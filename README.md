# ycappuccino-core

Framework de composants « à la Spring » pour Python, construit sur [Pelix/iPOPO](https://ipopo.readthedocs.io/). Tu écris des classes Python ordinaires ; le framework les découvre, injecte leurs dépendances par le constructeur, gère leur cycle de vie (`start`/`stop` async) et les publie comme services OSGi.

Les interfaces communes (`YCappuccinoComponent`, `IActivityLogger`, `IConfiguration`…) sont dans le dépôt `api`, récupéré automatiquement comme dépendance.

## Démarrage rapide

Prérequis : [uv](https://docs.astral.sh/uv/) et Python ≥ 3.10.

```bash
uv init --app myapp
cd myapp
uv add --editable ../core      # chemin vers ce dépôt ; api suit automatiquement
```

Arborescence de l'application :

```
myapp/
  conf/application.yml
  src/myapp/__init__.py
  src/myapp/greeting.py
```

`conf/application.yml` :

```yaml
name: myapp
bundle_prefix: myapp          # packages scannés pour trouver les composants
components:
  Greeter:
    greeting: Bonjour         # surcharge la valeur par défaut du constructeur
```

`src/myapp/greeting.py` :

```python
from abc import ABC

from ycappuccino.api.core import IActivityLogger
from ycappuccino.api.core_base import YCappuccinoComponent, YCappuccinoType


class IGreeter(YCappuccinoComponent, ABC):
    """interface : le service est publié sous le nom IGreeter"""

    def greet(self, name: str) -> str:
        raise NotImplementedError


class Greeter(IGreeter):
    def __init__(self, greeting: str = "Hello"):      # propriété
        self._greeting = greeting

    def greet(self, name: str) -> str:
        return f"{self._greeting} {name}!"

    async def start(self):
        pass

    async def stop(self):
        pass


class Welcome(YCappuccinoComponent):
    def __init__(
        self,
        greeter: IGreeter,                                          # dépendance
        logger: YCappuccinoType(IActivityLogger, "(name=main)"),    # dépendance filtrée
    ):
        self._greeter = greeter
        self._logger = logger

    async def start(self):
        self._logger.info(self._greeter.greet("world"))

    async def stop(self):
        self._logger.info("bye")
```

Lancement depuis le dossier de l'application :

```bash
uv run ycappuccino
```

`data/log/Log-Activity-main.log` contient alors `Bonjour world!`. Ctrl+C arrête l'application proprement : les `stop()` sont appelés et `bye` est loggé.

## Écrire un composant

Une classe est un composant si c'est une **sous-classe concrète de `YCappuccinoComponent`**, directement ou via une interface, définie dans un module d'un package listé dans `bundle_prefix`. Elle implémente `start()` et `stop()`, de préférence `async`, mais des méthodes synchrones sont acceptées.

### Injection par le constructeur

| Paramètre du constructeur | Effet |
|---|---|
| `greeter: IGreeter` | dépendance **obligatoire** : le composant ne démarre qu'une fois un `IGreeter` disponible, et s'arrête si ce service disparaît |
| `logger: YCappuccinoType(IActivityLogger, "(name=main)")` | dépendance filtrée par un filtre LDAP sur les propriétés du service |
| `config: IConfiguration \| None`, `Optional[IConfiguration]` ou `config: IConfiguration = None` | dépendance **optionnelle** : `None` si absente |
| `greeters: list[IGreeter]` | **collection** vivante de tous les `IGreeter` : optionnelle (liste vide si aucun), mise à jour à chaque arrivée ou départ de service |
| `count: int = 3` | **propriété** : valeur par défaut, surchargeable dans `application.yml`, publiée comme propriété du service |
| `name: str` sans valeur par défaut | erreur : le composant est ignoré et l'erreur est loggée |

Un type est injectable s'il hérite de `YCappuccinoComponent`. Les annotations en chaîne (`"IGreeter"`) sont résolues.

### Services publiés

Un composant est publié sous le nom de sa classe et sous le nom de chaque interface YCappuccino de sa hiérarchie : `Greeter` est publié comme `Greeter` et `IGreeter`. Les propriétés du constructeur sont des propriétés du service, donc filtrables par les autres. Par exemple, `ActivityLogger(name="main")` répond au filtre `(name=main)`.

Les composants natifs reçoivent l'objet réel de leurs dépendances. L'instance est nommée `module.Classe` et sa factory `module.Classe-Factory`, ce qui est utile dans la console Pelix.

### Suivre une collection de services

Pour recevoir tous les services d'un type au fil de leur arrivée et de leur départ, hérite de `YCappuccinoComponentBind` et type le paramètre de `bind` :

```python
from ycappuccino.api.core_base import YCappuccinoComponentBind


class GreeterRegistry(YCappuccinoComponentBind):
    def __init__(self):
        super().__init__()
        self.greeters = []

    async def bind(self, service: IGreeter):
        self.greeters.append(service)

    async def un_bind(self, service: IGreeter):
        self.greeters.remove(service)

    async def start(self):
        pass

    async def stop(self):
        pass
```

## Configuration : `conf/application.yml`

```yaml
name: myapp
bundle_prefix:                 # un package ou une liste
  - myapp
  - ycappuccino.storage
components:                    # propriétés, par nom de classe ou nom qualifié module.Classe
  Greeter:
    greeting: Bonjour
layers:                        # couches activées (motifs fnmatch acceptés)
  myapp_admin:
    active: true
    any_key: any_value         # lu par Framework.get_framework().get_layer_properties("myapp_admin")
config:
  http_server:
    active: true
    port: 8080
    ip: localhost
  shell:
    console: true              # console Pelix ; par défaut seulement si stdin est un terminal
```

### Couches

Une classe n'est chargée que si sa couche est active. Une classe de composant natif (sans décorateur) déclare directement l'attribut `__ycappuccino_layer__` :

```python
class AdminService(YCappuccinoComponent):
    __ycappuccino_layer__ = "myapp_admin"
    ...
```

Le décorateur `@Layer(name=...)` fait la même chose et reste utile pour les bundles iPOPO legacy, qui ne peuvent pas porter l'attribut directement dans leur définition de classe sans le décorateur. Une classe sans couche est toujours chargée. Un package peut déclarer les couches dont dépend la sienne dans `conf/config.yaml`, à côté de son `__init__.py` :

```yaml
layer: myapp_admin             # défaut : nom du package avec "." remplacé par "_"
dependencies_layer:
  myapp_audit: true            # activée automatiquement avec myapp_admin
```

## Composants fournis

| Composant | Service | Rôle |
|---|---|---|
| `Configuration` | `IConfiguration` | lit et écrit `conf/config.properties` dans le répertoire courant : `get(key, default)`, `set`, `has` ; `true`/`false` sont convertis en booléens |
| `ActivityLogger` | `IActivityLogger`, propriété `name=main` | logger fichier `data/log/Log-Activity-main.log`, réglable par `activity.logger.main.file`, `.level`, `.format`, `.nb`, `.size` dans `config.properties` |

## Installer un composant à l'exécution

`load_bundles()` scanne `bundle_prefix` une seule fois, au démarrage. Un code qui doit créer une instance de composant native plus tard — par exemple à partir d'une donnée stockée, découverte après coup — utilise directement `Framework.get_framework()` :

```python
handle = Framework.get_framework().instantiate_component(Greeter, {"greeting": "Salut"})
...
Framework.get_framework().destroy_component(handle)
```

- `component` est une classe de composant native (comme dans `bundle_prefix`), ou une chaîne `"module.Classe"` résolue par import ; `TypeError` si la classe n'est pas un composant natif valide (voir « Écrire un composant »), `ImportError` si le chemin ne se résout pas.
- `properties` surcharge les propriétés du constructeur, exactement comme `components: <nom>: {...}` dans `application.yml`.
- Chaque appel crée une instance **indépendante**, y compris pour la même classe appelée plusieurs fois : elle est publiée sous son nom qualifié suivi d'un compteur (`module.Classe#1`, `module.Classe#2`, ...), visible dans la console Pelix.
- `destroy_component(handle)` arrête (`stop()`) puis désinstalle l'instance ; appeler `destroy_component` une seconde fois sur le même handle ne fait rien.
- Le framework doit être démarré (`init()` déjà appelé) ; sinon `RuntimeError`.

**Sans threads (navigateur, Pyodide).** Où aucun thread ne peut démarrer, `AsyncRunner` exécute une coroutine de composant sur le thread appelant : elle s'achève de façon synchrone tant qu'elle n'attend pas un futur réellement en attente (le cas d'un `start()` ordinaire), si bien que les composants restent validés dans l'ordre ; si elle en attend un, `start()` rend la main et la suite continue comme tâche de la boucle de la page, ses erreurs journalisées. Aucune boucle n'est alors créée : sous Pyodide, en créer une remplacerait celle de la page.

**Piège : ne jamais appeler `instantiate_component`/`destroy_component` de façon synchrone depuis le `start()`/`stop()` d'un composant tant que celui-ci est encore en cours de validation/invalidation.** L'installation d'un bundle Pelix instancie et valide son composant sous un verrou global tenu pendant toute la validation, laquelle s'exécute (via `AsyncRunner`) sur un thread dédié différent de celui qui a démarré le bundle ; un appel imbriqué à `instantiate_component`/`destroy_component` depuis cette validation redemande ce même verrou, encore détenu par l'appel englobant — interblocage permanent, sans exception. Un composant qui doit réagir à un événement (`ITrigger`, service lié plus tard...) n'est pas concerné, seul un appel **synchrone depuis son propre `start()`/`stop()`** l'est ; s'il doit le faire au démarrage, qu'il le fasse dans un thread séparé qu'il ne bloque pas sur le résultat (voir `ycappuccino-component-creator`, `ComponentActivator.start()`, pour un exemple traité).

Ce mécanisme est le même que celui utilisé par `load_bundles()` pour les composants découverts au scan (`describe_component`, `create_factory_module`) ; il n'est pas lié à un modèle de données particulier — n'importe quel sous-projet peut l'utiliser pour piloter des instances de composants depuis ses propres données.

## Introspecter les composants natifs installés

`Framework.get_framework().list_components()` renvoie la liste des composants natifs actuellement installés dans ce `Framework` — ceux découverts au scan de `bundle_prefix` par `load_bundles()` **et** ceux créés à l'exécution par `instantiate_component()` (retirés de la liste par `destroy_component()`) :

```python
Framework.get_framework().list_components()
# [{"module": "myapp.greeting", "class": "Greeter", "provides": ["myapp.greeting.IGreeter", "myapp.greeting.Greeter"]}]
```

- `module` et `class` identifient la classe du composant lui-même (pas son instance).
- `provides` contient, pour chaque spécification publiée par le composant, son **chemin qualifié** `module.NomDeClasse` uniquement (pas les noms courts utilisés par Pelix, comme `IGreeter` — pour ceux-là, appelle `describe_component` directement). C'est exactement `ComponentDescription.provides_qualified`, le pendant qualifié de `ComponentDescription.provides` produit par `describe_component()` : les deux listes sont alignées index à index (`provides[i]` et `provides_qualified[i]` désignent la même spécification, l'un sous forme de nom court utilisé tel quel comme `objectClass` Pelix, l'autre sous forme de chemin qualifié). Un chemin qualifié se résout en la classe réelle avec `ycappuccino.core.component_factory.resolve_class(chemin)` — c'est l'usage prévu de `provides` : retrouver, à partir d'un nom court découvert ailleurs (par exemple via la console Pelix ou un service Pelix), la classe Python correspondante sans avoir à la connaître d'avance.
- **Les bundles iPOPO legacy (classes décorées `@ComponentFactory`, installées telles quelles comme bundle Pelix) ne sont pas dans cette liste** : ils n'existent pas sous forme de `ComponentDescription`, `describe_component` ne leur est jamais appliqué. Seuls les composants natifs (voir « Écrire un composant ») y figurent.
- `Framework.stop()` vide cette liste.

**Piège de timing, à connaître avant de construire quoi que ce soit dessus.** Le motif recommandé pour créer un composant au démarrage sans provoquer l'interblocage documenté ci-dessus (« Installer un composant à l'exécution ») est de lancer l'appel à `instantiate_component` depuis un thread séparé, sans l'attendre (voir `ycappuccino-component-creator`, `ComponentActivator.start()`) — le `start()` du composant découvreur revient donc *avant* que les instances qu'il crée n'existent réellement. Or `load_bundles()` scanne et instancie tous les composants d'un même `bundle_prefix` en une seule passe, dans un ordre non garanti : rien n'assure qu'un composant scanné après le découvreur, dans cette même passe, voie déjà exister les instances que celui-ci crée en arrière-plan — ni `list_components()`, ni les services Pelix qu'elles publient. Ce n'est pas un défaut de `list_components()` ni d'`instantiate_component()` : c'est la conséquence directe, inévitable, du fait d'éviter l'interblocage en ne bloquant pas sur le résultat. En pratique, tout code qui utiliserait `list_components()` et `instantiate_component()` pour satisfaire la **dépendance obligatoire** d'un autre composant natif doit soit tolérer une arrivée tardive (dépendance optionnelle ou collection, jamais requise au sens strict), soit lui-même être créé dynamiquement après coup plutôt que découvert par le scan normal — jamais supposer que la création dynamique a eu le temps de se terminer avant que le scan `bundle_prefix` de la même passe n'ait fini d'instancier les autres composants.

## Servlets HTTP

Un composant qui implémente `IHttpServlet` (`ycappuccino.api.http`) devient une servlet Pelix, sans aucun décorateur :

```python
from ycappuccino.api.http import HttpRequest, HttpResponse, IHttpServlet


class Echo(IHttpServlet):

    def __init__(self, path: str = "/echo"):
        self._path = path

    async def handle(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=200, body=b"{}", content_type="application/json")

    async def start(self):
        pass

    async def stop(self):
        pass
```

`path` est une propriété ordinaire (surchargeable dans `application.yml`, `components: Echo: {path: /autre}`) : le framework l'expose aussi comme le chemin de la servlet Pelix. `handle` est appelée depuis le thread HTTP de Pelix, via le même pont synchrone que `start`/`stop` ; une exception qu'elle laisse s'échapper devient une réponse `500`. Cela suppose `config.http_server.active: true` dans `application.yml`.

## Lancer une application

```bash
uv run ycappuccino [--root_path DIR] [--config_yml_path conf/application.yml]
# équivalent : uv run python -m ycappuccino.core.runner
```

- **Configuration :** `application.yml` est lu dans `<root_path>/<config_yml_path>` ; `root_path` vaut `.` par défaut.
- **Répertoire courant :** il compte. Il est ajouté au `sys.path`, `config.properties` y est lu et `data/log` y est écrit.
- **Console Pelix :** elle permet d'inspecter l'application ; `help` liste les commandes, dont celles d'iPOPO sur les factories et les instances.
- **Arrêt :** Ctrl+C arrête proprement ; SIGTERM n'est pas intercepté.

## Modèles et bundles iPOPO existants

- **Modèles :** les classes `@Item` (`ycappuccino.api.decorators`) trouvées pendant le scan sont enregistrées, et le chemin de leur module est exposé par `Framework.get_framework().bundle_models_loaded_path_by_name`. Leur persistance est assurée par `ycappuccino-storage`.
- **Bundles iPOPO :** un module qui contient des classes décorées avec `@ComponentFactory` est installé tel quel comme bundle Pelix, sous réserve de sa `@Layer`. Ce mode existe pour la compatibilité ; les nouveaux composants s'écrivent en style natif.
- **Imports en échec :** un module qui ne s'importe pas est ignoré avec un warning, sans arrêter l'application.

## Tester ses composants

**Test unitaire :** un composant est une classe Python ordinaire, instanciable avec des doublures.

```python
import unittest
from unittest import mock

from myapp.greeting import Welcome


class FakeGreeter:
    def greet(self, name):
        return f"hi {name}"


class TestWelcome(unittest.IsolatedAsyncioTestCase):
    async def test_start_logs_a_greeting(self):
        logger = mock.Mock()
        await Welcome(FakeGreeter(), logger).start()
        logger.info.assert_called_once_with("hi world")
```

**Test d'intégration :** on démarre le vrai framework sur un `application.yml` de test. Un seul framework Pelix peut exister par processus, donc il faut toujours appeler `stop()`.

```python
from ycappuccino.core.framework import Framework


class TestApplication(unittest.TestCase):
    def test_greeter_is_published(self):
        framework = Framework()
        framework.init("tests/conf/application.yml")
        self.addCleanup(framework.stop)

        reference = framework.context.get_service_reference("IGreeter")
        greeter = framework.context.get_service(reference)
        self.assertEqual(greeter.greet("test"), "Bonjour test!")
```

Pour ne pas écrire l'application de test à la main, `ycappuccino.core.testing.TemporaryApplication` crée un `application.yml` et un package dans un dossier temporaire (le texte `PACKAGE` est remplacé par un nom unique) et en fait le répertoire courant. `wait_until(predicate)` attend qu'une condition devienne vraie.

```python
from ycappuccino.core.testing import TemporaryApplication

app = TemporaryApplication({
    "conf/application.yml": "bundle_prefix: PACKAGE\n",
    "PACKAGE/__init__.py": "",
    "PACKAGE/greeting.py": "...",
}).open()
self.addCleanup(app.close)
```

## Développer core

```bash
uv sync
uv run python -m unittest discover -s src/unittest/python
```

L'exemple `example/` se lance avec `cd example && uv run --project .. ycappuccino`.
