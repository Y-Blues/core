# Composants HTTP natifs : design

Date : 2026-09-15. Sous-projet 0 (prérequis core) de la reprise des dépôts YCappuccino, avant `http_server`. Couvre C1 (servlets HTTP sans décorateur) et C2 (remplacement de `@Layer`) de `ROADMAP.md`.

## Objectif

Permettre à un composant natif (classe simple, injection par constructeur, méthodes `async`) d'être publié comme servlet Pelix, sans aucun décorateur sur la classe. `http_server`, puis `hosts` et `swagger`, l'utiliseront pour exposer leurs services en HTTP.

## Décisions

| Sujet | Décision |
|---|---|
| Comment un composant devient servlet | Il implémente une interface `IHttpServlet` d'`api` ; `core` reconnaît cette interface à la génération de la factory et ajoute les specs/propriétés Pelix nécessaires |
| Décorateur sur le composant | Aucun ; `IHttpServlet` est une ABC ordinaire, comme les autres interfaces YCappuccino |
| `api` et Pelix | `api.http.py` (nouveau module) ne importe pas Pelix : `HttpRequest`/`HttpResponse` sont des dataclasses ordinaires ; c'est `core` qui connaît `pelix.http` |
| Serveur Pelix | `pelix.http.basic` (le même que l'existant, thread par requête), pas `pelix.http.basic_async` : `handle` reste appelée de façon synchrone depuis le thread de la requête, via `AsyncRunner.run`, comme `start`/`stop` aujourd'hui |
| Chemin de la servlet | Paramètre de constructeur `path: str`, comme n'importe quelle propriété ; sa valeur résolue (défaut ou surchargée par `application.yml`) est aussi exposée sous la clé Pelix `pelix.http.path` |
| `@Layer` | Remplacé par un attribut de classe direct `__ycappuccino_layer__ = "nom"` (ce que fait déjà le décorateur) ; aucun changement de `core` n'est nécessaire, seulement des classes qui n'utilisent plus le décorateur |

## 1. `api.http` : contrat sans Pelix

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ycappuccino.api.core_base import YCappuccinoComponent


@dataclass
class HttpRequest:
    """requête HTTP reçue par une servlet, sans dépendance à Pelix"""
    method: str                          # "GET", "POST", "PUT", "DELETE", ...
    path: str                            # chemin complet de la requête, sans la query string
    prefix: str                          # préfixe enregistré de la servlet (sa propriété path)
    sub_path: str                        # path, débarrassé du préfixe
    query: dict                          # paramètres de la query string, valeurs texte
    headers: dict                        # noms d'en-têtes en minuscules
    body: bytes = b""


@dataclass
class HttpResponse:
    """réponse renvoyée par une servlet"""
    status: int
    body: bytes = b""
    content_type: str = "application/json"
    headers: dict = field(default_factory=dict)


class IHttpServlet(YCappuccinoComponent, ABC):
    """composant qui répond aux requêtes HTTP reçues sous son path"""

    @abstractmethod
    async def handle(self, request: HttpRequest) -> HttpResponse:
        """traite la requête et renvoie la réponse"""
```

Une classe qui implémente `IHttpServlet` doit avoir un paramètre de constructeur `path: str` avec une valeur par défaut (une propriété ordinaire, surchargeable par `application.yml`, `components: <Nom>: {path: /autre}`). Son absence lève une erreur explicite à la description du composant (même traitement que les erreurs de description existantes : loguée, composant ignoré).

## 2. `core` : reconnaissance d'`IHttpServlet`

Dans `describe_component` / `create_factory_module` (`component_factory.py`) :

- Après avoir construit la description normale du composant (specs, dépendances, propriétés), si la classe implémente `IHttpServlet` :
  - la spec Pelix `pelix.http.HTTP_SERVLET` est ajoutée à celles fournies par le composant (`description.provides`), en plus de `IHttpServlet` et des autres specs YCappuccino déjà calculées ;
  - la valeur résolue de la propriété `path` (celle après fusion avec `application.yml`, donc déjà présente dans `instance_properties` ou dans la valeur par défaut du constructeur) est copiée sous la clé `pelix.http.HTTP_SERVLET_PATH` des propriétés d'instance passées à `Instantiate` ;
  - la spec `pelix.remote.PROP_EXPORT_REJECT` est ajoutée avec la valeur `pelix.http.HTTP_SERVLET`, comme le faisait la servlet legacy, pour qu'une servlet ne soit jamais exportée en remote.
- Le proxy généré (`Proxy` créé par `create_factory_module`) reçoit quatre méthodes synchrones `do_GET`, `do_POST`, `do_PUT`, `do_DELETE`, présentes seulement si la classe implémente `IHttpServlet`. Chacune :
  1. construit un `HttpRequest` à partir de l'objet `AbstractHTTPServletRequest` de Pelix (`get_path()`, `get_prefix_path()`, `get_headers()`, `read_data()`) et de la méthode HTTP correspondante ; la query string est extraite de `get_path()` avec `urllib.parse` et retirée du `path`/`sub_path` ;
  2. appelle `runner.run(self._obj.handle(request))`, exactement comme `validate`/`invalidate` appellent déjà `runner.run(self._obj.start())` ;
  3. traduit le `HttpResponse` renvoyé vers l'objet `AbstractHTTPServletResponse` de Pelix : `set_header` pour chaque en-tête, puis `send_content(status, body, content_type)`.
  4. si `handle` lève une exception, elle est loguée et traduite en `HttpResponse(500, ...)` avant traduction — une servlet ne doit jamais laisser une exception remonter dans le thread HTTP de Pelix.
- Aucun changement à la génération des servlets n'est requis pour un composant qui n'implémente pas `IHttpServlet` : le comportement actuel est inchangé.

## 3. `@Layer` : suppression du décorateur

`Layer.__call__` (`decorator_app.py`) fait exactement `setattr(obj, utils.LAYER_ATTRIBUTE, name)`, et `framework.py` lit cet attribut par `getattr(klass, utils.LAYER_ATTRIBUTE, None)`, sans jamais passer par le décorateur lui-même. Une classe peut donc déclarer directement :

```python
class MemoryStorage(IStorage):
    __ycappuccino_layer__ = "ycappuccino_storage_memory"
```

au lieu de `@Layer(name="ycappuccino_storage_memory")`. Aucun changement de `core` n'est nécessaire. Ce sous-projet applique ce remplacement aux deux backends de `storage` (`MemoryStorage`, `MongoStorage`) pour qu'aucun composant natif ne porte plus de décorateur de framework, conformément à la règle de style : les classes de composants restent des implémentations ordinaires, testables sans le framework ; seul le proxy iPOPO généré par `core` est un artefact du framework.

`@App` reste un décorateur sur les **modèles** (`@Item`), pas sur des composants ; il n'est pas concerné par cette règle et n'est pas modifié ici.

## 4. Hors périmètre

- `http_server` lui-même : sous-projet suivant, qui utilisera `IHttpServlet`.
- `pelix.http.basic_async` / servlets asynchrones natifs : non nécessaire tant que le pont synchrone via `AsyncRunner` suffit ; à reconsidérer si le volume de requêtes concurrentes devient un problème (un thread par requête).
- Le routage interne à une servlet (par exemple les multiples routes de `http_server`) : à la charge de chaque implémentation d'`IHttpServlet`, pas de `core`.
- Remplacement de `@App` : hors périmètre, ce n'est pas un décorateur de composant.

## 5. Risques

- **Un thread par requête** (comme aujourd'hui) : limite le débit sous forte concurrence ; documenté comme non-objectif de ce sous-projet.
- **Chemin non surchargé côté Pelix** : si `application.yml` ne fournit pas `path`, la valeur par défaut du constructeur est utilisée pour les deux propriétés (`path` et `pelix.http.path`) ; elles doivent donc toujours rester synchronisées, ce que garantit le mécanisme (une seule valeur résolue, copiée vers les deux clés).
