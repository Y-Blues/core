# Composants HTTP natifs : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à un composant natif d'être publié comme servlet Pelix en implémentant une interface `IHttpServlet` d'`api`, sans aucun décorateur, et remplacer `@Layer` par un attribut de classe direct sur les backends de `storage`.

**Architecture:** `api.http` ajoute `HttpRequest`/`HttpResponse` (dataclasses) et `IHttpServlet` (ABC), sans import Pelix. `core.component_factory` reconnaît `IHttpServlet` : `describe_component` ajoute la spec `pelix.http.servlet` (testable sans framework), `create_factory_module` ajoute la propriété `pelix.http.path`, le rejet d'export remote, et génère les méthodes `do_GET`/`do_POST`/`do_PUT`/`do_DELETE` du proxy qui pontent vers `handle()` via `AsyncRunner`, comme `start`/`stop` aujourd'hui. `storage` remplace `@Layer(name=...)` par `__ycappuccino_layer__ = "..."` sur ses deux backends.

**Tech Stack:** Python ≥ 3.10, uv, Pelix/iPOPO 3 (`pelix.http`), unittest (`unittest.IsolatedAsyncioTestCase` pour l'async, `unittest.TestCase` pour l'intégration framework), `urllib` (stdlib, pour l'appel HTTP réel du test d'intégration).

**Spec:** `core/docs/superpowers/specs/2026-09-15-http-servlet-design.md`

## Global Constraints

- Chemins relatifs à la racine du workspace `/home/apisu/Documents/perso/repositories` ; `api`, `core`, `storage` sont des dépôts git séparés.
- **Aucun commit** : l'utilisateur commite lui-même (la permission de commit a été refusée par l'outil malgré l'accord de l'utilisateur ; ne pas retenter). Chaque tâche se termine par la vérification des tests.
- Commande de test, lancée depuis le dépôt concerné : `uv run python -m unittest discover -s src/unittest/python`.
- **Aucun décorateur sur les classes de composants** : `IHttpServlet` est une ABC ordinaire ; les backends `storage` remplacent `@Layer` par l'attribut direct `__ycappuccino_layer__`. Seul le proxy iPOPO généré par `core` est un artefact du framework.
- `api.http` n'importe pas Pelix (ni directement, ni transitivement) : les dataclasses et l'ABC doivent rester utilisables hors du framework (client pyscript).
- Le serveur HTTP reste `pelix.http.basic` (thread par requête) ; `handle()` est appelée de façon synchrone par le proxy via `AsyncRunner.run`, comme `start`/`stop`.
- Specs Pelix : `pelix.http.HTTP_SERVLET` (valeur `"pelix.http.servlet"`), `pelix.http.HTTP_SERVLET_PATH` (valeur `"pelix.http.path"`), `pelix.remote.PROP_EXPORT_REJECT`.

## Structure des fichiers

| Fichier | Responsabilité |
|---|---|
| `api/src/main/python/ycappuccino/api/http.py` (créé) | `HttpRequest`, `HttpResponse`, `IHttpServlet` |
| `api/src/unittest/python/test_http.py` (créé) | tests de `api.http` |
| `core/src/main/python/ycappuccino/core/component_factory.py` (modifié) | reconnaissance d'`IHttpServlet` dans `describe_component` et `create_factory_module` |
| `core/src/unittest/python/test_component_factory.py` (modifié) | tests unitaires de la spec ajoutée et du paramètre `path` obligatoire |
| `core/src/unittest/python/test_http_servlet_framework.py` (créé) | test d'intégration : servlet native, vrai serveur HTTP, vraie requête |
| `core/README.md` (modifié) | section « Servlets HTTP », section « Couches » mise à jour |
| `storage/src/main/python/ycappuccino/storage/memory.py`, `mongo.py` (modifiés) | `__ycappuccino_layer__` au lieu de `@Layer` |
| `CLAUDE.md` (racine du workspace, modifié) | mention de la forme sans décorateur des couches |

---

### Task 1: api, `HttpRequest`/`HttpResponse`/`IHttpServlet`

**Files:**
- Create: `api/src/main/python/ycappuccino/api/http.py`
- Test: `api/src/unittest/python/test_http.py`

**Interfaces:**
- Produces: `ycappuccino.api.http` avec `HttpRequest(method, path, prefix, sub_path, query, headers, body=b"")`, `HttpResponse(status, body=b"", content_type="application/json", headers={})` (dataclasses ordinaires), et `IHttpServlet(YCappuccinoComponent, ABC)` avec `async def handle(self, request: HttpRequest) -> HttpResponse`.

- [ ] **Step 1: Write the failing test**

`api/src/unittest/python/test_http.py` :

```python
import dataclasses
import inspect
import unittest

from ycappuccino.api.core_base import YCappuccinoComponent
from ycappuccino.api.http import HttpRequest, HttpResponse, IHttpServlet


class TestHttpRequest(unittest.TestCase):

    def test_is_a_plain_dataclass(self):
        self.assertTrue(dataclasses.is_dataclass(HttpRequest))
        request = HttpRequest(
            method="GET", path="/api/books", prefix="/api", sub_path="/books",
            query={"limit": "5"}, headers={"authorization": "Bearer x"},
        )
        self.assertEqual(request.body, b"")

    def test_no_pelix_import(self):
        import ycappuccino.api.http as module
        self.assertNotIn("pelix", module.__name__)
        for name, value in vars(module).items():
            if inspect.ismodule(value):
                self.assertFalse(value.__name__.startswith("pelix"), name)


class TestHttpResponse(unittest.TestCase):

    def test_defaults(self):
        response = HttpResponse(status=200)
        self.assertEqual(response.body, b"")
        self.assertEqual(response.content_type, "application/json")
        self.assertEqual(response.headers, {})

    def test_headers_default_is_not_shared(self):
        HttpResponse(status=200).headers["x"] = "1"
        self.assertEqual(HttpResponse(status=200).headers, {})


class TestIHttpServlet(unittest.TestCase):

    def test_is_abstract_component(self):
        self.assertTrue(issubclass(IHttpServlet, YCappuccinoComponent))
        self.assertTrue(inspect.isabstract(IHttpServlet))

    def test_handle_is_a_coroutine(self):
        self.assertTrue(inspect.iscoroutinefunction(IHttpServlet.handle))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run (depuis `api`) : `uv run python -m unittest discover -s src/unittest/python -p test_http.py`
Expected: `ModuleNotFoundError: No module named 'ycappuccino.api.http'`.

- [ ] **Step 3: Write minimal implementation**

`api/src/main/python/ycappuccino/api/http.py` :

```python
"""
api.http: contract of a component that answers HTTP requests, without any dependency on Pelix.

HttpRequest and HttpResponse are plain dataclasses so this module stays importable outside the
framework (e.g. the pyscript client). ycappuccino.core translates them to and from the real
Pelix HTTP servlet API for a component that implements IHttpServlet.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional

from ycappuccino.api.core_base import YCappuccinoComponent


@dataclass
class HttpRequest:
    """HTTP request received by a servlet"""
    method: str
    path: str
    prefix: str
    sub_path: str
    query: dict
    headers: dict
    body: bytes = b""


@dataclass
class HttpResponse:
    """HTTP response returned by a servlet"""
    status: int
    body: bytes = b""
    content_type: str = "application/json"
    headers: dict = field(default_factory=dict)


class IHttpServlet(YCappuccinoComponent, ABC):
    """component answering the HTTP requests received under its path property"""

    @abstractmethod
    async def handle(self, request: HttpRequest) -> HttpResponse:
        """process the request and return the response"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run (depuis `api`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK`.

---

### Task 2: core, `describe_component` reconnaît `IHttpServlet`

**Files:**
- Modify: `core/src/main/python/ycappuccino/core/component_factory.py`
- Test: `core/src/unittest/python/test_component_factory.py`

**Interfaces:**
- Consumes (Task 1): `ycappuccino.api.http.IHttpServlet`.
- Produces: `describe_component(klass).provides` contient `"pelix.http.servlet"` (en plus des specs YCappuccino habituelles) quand `klass` implémente `IHttpServlet`. Décrire un tel composant sans paramètre de constructeur `path: str` (avec valeur par défaut) lève `TypeError`, journalisée comme les autres composants mal décrits.

- [ ] **Step 1: Write the failing test**

Ajouter à `core/src/unittest/python/test_component_factory.py`, après les imports existants :

```python
from ycappuccino.api.http import HttpRequest, HttpResponse, IHttpServlet
```

et, dans la section des classes de test (après `LegacyGreeter`) :

```python
class Servlet(Lifecycle, IHttpServlet):

    def __init__(self, path: str = "/api"):
        self._path = path

    async def handle(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=200)


class ServletWithoutPath(Lifecycle, IHttpServlet):

    def __init__(self):
        pass

    async def handle(self, request: HttpRequest) -> HttpResponse:
        return HttpResponse(status=200)
```

Puis, dans `TestDescribeComponent`, avant la fin de la classe :

```python
    def test_http_servlet_provides_the_pelix_servlet_spec(self):
        self.assertEqual(
            describe_component(Servlet).provides,
            ["Servlet", "IHttpServlet", "pelix.http.servlet"],
        )

    def test_http_servlet_without_a_path_parameter_is_rejected(self):
        with self.assertRaises(TypeError):
            describe_component(ServletWithoutPath)
```

- [ ] **Step 2: Run test to verify it fails**

Run (depuis `core`) : `uv run python -m unittest discover -s src/unittest/python -p test_component_factory.py`
Expected: `AssertionError` : `provides` ne contient pas `"pelix.http.servlet"` ; `ServletWithoutPath` ne lève pas `TypeError` (aucun paramètre à décrire, donc pas d'erreur actuellement).

- [ ] **Step 3: Implement**

Dans `component_factory.py`, ajouter l'import :

```python
import pelix.http as http
```

Et dans `_provided_specifications` ou juste après son appel dans `describe_component`, ajouter la spec servlet. Modifier `describe_component` :

```python
def describe_component(klass: type) -> ComponentDescription:
    ...
    description = ComponentDescription(klass, provides=_provided_specifications(klass))
    ...
    if issubclass(klass, IHttpServlet):
        description.provides.append(http.HTTP_SERVLET)
        if "path" not in description.properties:
            raise TypeError(f"{klass.__qualname__} implements IHttpServlet but declares no 'path' property")
    return description
```

(l'emplacement exact dépend du code existant de `describe_component` : la vérification de `path` doit avoir lieu après que les propriétés du constructeur ont été calculées, donc en fin de fonction, juste avant le `return`). Ajouter l'import :

```python
from ycappuccino.api.http import IHttpServlet
```

- [ ] **Step 4: Run tests to verify they pass**

Run (depuis `core`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK`.

---

### Task 3: core, génération du proxy servlet

**Files:**
- Modify: `core/src/main/python/ycappuccino/core/component_factory.py`
- Test: `core/src/unittest/python/test_http_servlet_framework.py`

**Interfaces:**
- Consumes (Task 1): `HttpRequest`, `HttpResponse`, `IHttpServlet`. (Task 2): `describe_component` ajoute déjà `pelix.http.servlet` à `provides`.
- Produces: pour un composant implémentant `IHttpServlet`, `create_factory_module` génère un proxy qui, en plus du comportement existant :
  - expose la propriété Pelix `pelix.http.HTTP_SERVLET_PATH` avec la valeur résolue de `path` (celle après fusion avec `application.yml`) ;
  - expose `pelix.remote.PROP_EXPORT_REJECT` avec la valeur `pelix.http.HTTP_SERVLET` ;
  - fournit `do_GET(request, response)`, `do_POST(request, response)`, `do_PUT(request, response)`, `do_DELETE(request, response)` qui traduisent la requête/réponse Pelix vers/depuis `HttpRequest`/`HttpResponse` et appellent `runner.run(self._obj.handle(request))` ; une exception de `handle` est journalisée et traduite en `HttpResponse(500, ...)`.

- [ ] **Step 1: Write the failing integration test**

`core/src/unittest/python/test_http_servlet_framework.py` :

```python
import json
import unittest
import urllib.error
import urllib.request

from ycappuccino.core.framework import Framework
from ycappuccino.core.testing import TemporaryApplication, wait_until

PORT = 18080

APPLICATION = {
    "conf/application.yml": """
        name: httptest
        bundle_prefix: PACKAGE
        config:
          http_server:
            active: true
            port: {port}
            ip: localhost
          shell:
            console: false
    """.replace("{port}", str(PORT)),
    "PACKAGE/__init__.py": "",
    "PACKAGE/servlet.py": """
        import json

        from ycappuccino.api.core_base import YCappuccinoComponent
        from ycappuccino.api.http import HttpRequest, HttpResponse, IHttpServlet


        class Echo(IHttpServlet):

            def __init__(self, path: str = "/echo"):
                self._path = path

            async def handle(self, request: HttpRequest) -> HttpResponse:
                if request.sub_path == "/boom":
                    raise RuntimeError("boom")
                body = json.dumps(
                    {"method": request.method, "sub_path": request.sub_path, "query": request.query}
                ).encode()
                return HttpResponse(status=201, body=body, headers={"x-echo": "1"})

            async def start(self):
                pass

            async def stop(self):
                pass
    """,
}


class TestHttpServletInFramework(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = TemporaryApplication(APPLICATION).open()
        cls.addClassCleanup(cls.app.close)
        cls.framework = Framework()
        cls.framework.init(cls.app.yml_path)
        cls.addClassCleanup(cls.framework.stop)
        wait_until(lambda: cls.framework.context.get_service_reference("Echo"))

    def request(self, method, path, body=None):
        req = urllib.request.Request(f"http://localhost:{PORT}{path}", data=body, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, dict(response.getheaders()), response.read()
        except urllib.error.HTTPError as error:
            return error.code, dict(error.headers), error.read()

    def test_get_is_routed_to_handle(self):
        status, headers, body = self.request("GET", "/echo/books?limit=5")

        self.assertEqual(status, 201)
        self.assertEqual(headers.get("x-echo"), "1")
        self.assertEqual(json.loads(body), {"method": "GET", "sub_path": "/books", "query": {"limit": "5"}})

    def test_post_is_routed_to_handle(self):
        status, _, body = self.request("POST", "/echo/create", body=b"{}")

        self.assertEqual(status, 201)
        self.assertEqual(json.loads(body)["method"], "POST")

    def test_unhandled_exception_becomes_a_500(self):
        status, _, _ = self.request("GET", "/echo/boom")

        self.assertEqual(status, 500)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test to verify it fails**

Run (depuis `core`) : `uv run python -m unittest discover -s src/unittest/python -p test_http_servlet_framework.py`
Expected: la servlet ne répond pas avec le comportement attendu (`do_GET`/`do_POST` absents du proxy, ou `path` non exposé comme `pelix.http.path`) ; connexion refusée ou 404 selon le point d'échec.

- [ ] **Step 3: Implement**

Dans `create_factory_module` (`component_factory.py`), après la construction de `namespace` et avant l'application des décorateurs `Requires`/`Property` existants :

```python
if issubclass(component, IHttpServlet):
    def _http_request(pelix_request, method: str) -> "HttpRequest":
        from urllib.parse import parse_qsl, urlsplit
        full_path = pelix_request.get_path()
        query = dict(parse_qsl(urlsplit(full_path).query))
        return HttpRequest(
            method=method,
            path=urlsplit(full_path).path,
            prefix=pelix_request.get_prefix_path(),
            sub_path=urlsplit(pelix_request.get_sub_path()).path,
            query=query,
            headers=dict(pelix_request.get_headers()),
            body=pelix_request.read_data() or b"",
        )

    def _send(pelix_response, http_response: "HttpResponse") -> None:
        for name, value in http_response.headers.items():
            pelix_response.set_header(name, value)
        pelix_response.send_content(http_response.status, http_response.body, http_response.content_type)

    def _do(method: str):
        def handler(self, pelix_request, pelix_response):
            request = _http_request(pelix_request, method)
            try:
                result = runner.run(self._obj.handle(request))
            except Exception:
                import logging
                logging.getLogger(component.__module__).exception("servlet %s failed on %s", component.__qualname__, request.path)
                result = HttpResponse(status=500, body=b"", content_type="text/plain")
            _send(pelix_response, result)
        return handler

    for verb in ("GET", "POST", "PUT", "DELETE"):
        namespace[f"do_{verb}"] = _do(verb)
```

Ajouter les imports nécessaires en tête de fichier :

```python
import pelix.remote
from ycappuccino.api.http import HttpRequest, HttpResponse, IHttpServlet
```

Puis, après la construction de `factory_class` et avant `factory_class = Provides(description.provides)(factory_class)`, ajouter les propriétés spécifiques à la servlet :

```python
if issubclass(component, IHttpServlet):
    path_value = (instance_properties or {}).get("path", description.properties.get("path"))
    factory_class = Property("_ycappuccino_http_path", http.HTTP_SERVLET_PATH, path_value)(factory_class)
    factory_class = Property(
        "_ycappuccino_http_reject", pelix.remote.PROP_EXPORT_REJECT, http.HTTP_SERVLET
    )(factory_class)
```

(`http` est déjà importé en tête de fichier depuis la Task 2 ; si `create_factory_module` et `describe_component` sont dans des sections différentes du même fichier, un seul import suffit). Vérifier que `pelix.remote` expose bien `PROP_EXPORT_REJECT` (sinon, importer `from pelix.remote import PROP_EXPORT_REJECT` directement).

- [ ] **Step 4: Run tests to verify they pass**

Run (depuis `core`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK`. Si un port est déjà occupé sur la machine de test, changer `PORT` dans le test et documenter le choix dans le rapport.

---

### Task 4: storage, `@Layer` remplacé par l'attribut direct

**Files:**
- Modify: `storage/src/main/python/ycappuccino/storage/memory.py`
- Modify: `storage/src/main/python/ycappuccino/storage/mongo.py`

**Interfaces:**
- Consumes: rien de nouveau ; `framework.py` lit déjà `getattr(klass, "__ycappuccino_layer__", None)`, indépendamment de la présence du décorateur.

- [ ] **Step 1: Replace the decorator**

Dans `storage/src/main/python/ycappuccino/storage/memory.py`, remplacer :

```python
from ycappuccino.core.decorator_app import Layer
from ycappuccino.storage.query import MISSING, get_path

_COMPARISONS = {
```

par :

```python
from ycappuccino.storage.query import MISSING, get_path

_COMPARISONS = {
```

et remplacer :

```python
@Layer(name="ycappuccino_storage_memory")
class MemoryStorage(IStorage):

    def __init__(self):
```

par :

```python
class MemoryStorage(IStorage):
    __ycappuccino_layer__ = "ycappuccino_storage_memory"

    def __init__(self):
```

Dans `storage/src/main/python/ycappuccino/storage/mongo.py`, remplacer :

```python
from ycappuccino.api.storage import IStorage
from ycappuccino.core.decorator_app import Layer

_logger = logging.getLogger(__name__)


@Layer(name="ycappuccino_storage_mongo")
class MongoStorage(IStorage):

    def __init__(
```

par :

```python
from ycappuccino.api.storage import IStorage

_logger = logging.getLogger(__name__)


class MongoStorage(IStorage):
    __ycappuccino_layer__ = "ycappuccino_storage_mongo"

    def __init__(
```

- [ ] **Step 2: Run tests to verify they still pass**

Run (depuis `storage`) : `uv run python -m unittest discover -s src/unittest/python`
Expected: `OK`, même nombre de tests qu'avant (comportement inchangé ; `test_storage_framework.py` vérifie déjà que seul le backend de la couche active est démarré).

---

### Task 5: documentation et vérification finale

**Files:**
- Modify: `core/README.md`
- Modify: `CLAUDE.md` (racine du workspace)

**Interfaces:**
- Consumes: tout ce qui précède.

- [ ] **Step 1: Document IHttpServlet in core/README.md**

Dans `core/README.md`, section « Composants fournis » ou juste après la section « Couches », ajouter une nouvelle section :

```markdown
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
```

- [ ] **Step 2: Update the Couches section**

Dans `core/README.md`, remplacer le paragraphe :

```markdown
Une classe décorée par `@Layer` n'est chargée que si sa couche est active :

```python
from ycappuccino.core.decorator_app import Layer


@Layer(name="myapp_admin")
class AdminService(YCappuccinoComponent):
    ...
```

Une classe sans `@Layer` est toujours chargée.
```

par :

```markdown
Une classe n'est chargée que si sa couche est active. Une classe de composant natif (sans décorateur) déclare directement l'attribut `__ycappuccino_layer__` :

```python
class AdminService(YCappuccinoComponent):
    __ycappuccino_layer__ = "myapp_admin"
    ...
```

Le décorateur `@Layer(name=...)` fait la même chose et reste utile pour les bundles iPOPO legacy, qui ne peuvent pas porter l'attribut directement dans leur définition de classe sans le décorateur. Une classe sans couche est toujours chargée.
```

- [ ] **Step 3: Update the workspace CLAUDE.md**

Dans `CLAUDE.md`, remplacer :

```markdown
- `@Layer(name=...)` sets `__ycappuccino_layer__` on the class. A class without a layer is always loaded.
```

par :

```markdown
- A class is active only when its layer is active. `@Layer(name=...)` sets `__ycappuccino_layer__` on the class; a native component class can set that attribute directly instead (no decorator on component classes — see `ycappuccino.api.http.IHttpServlet` for the same rule applied to HTTP servlets). A class without a layer is always loaded.
```

- [ ] **Step 4: Final verification**

Run, depuis chaque dépôt, dans cet ordre :

```bash
cd api && uv run python -m unittest discover -s src/unittest/python
cd ../core && uv run python -m unittest discover -s src/unittest/python
cd ../storage && uv run python -m unittest discover -s src/unittest/python
```

Expected: `OK` pour les trois dépôts (tests Mongo de `storage` ignorés sans Docker).
