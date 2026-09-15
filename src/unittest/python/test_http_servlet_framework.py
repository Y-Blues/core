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
            with error:
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


PORT_OVERRIDE = 18081

APPLICATION_WITH_OVERRIDE = {
    "conf/application.yml": """
        name: httptest-override
        bundle_prefix: PACKAGE
        config:
          http_server:
            active: true
            port: {port}
            ip: localhost
          shell:
            console: false
        components:
          Echo:
            path: /override
    """.replace("{port}", str(PORT_OVERRIDE)),
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


class TestHttpServletPathOverride(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = TemporaryApplication(APPLICATION_WITH_OVERRIDE).open()
        cls.addClassCleanup(cls.app.close)
        cls.framework = Framework()
        cls.framework.init(cls.app.yml_path)
        cls.addClassCleanup(cls.framework.stop)
        wait_until(lambda: cls.framework.context.get_service_reference("Echo"))

    def request(self, method, path, body=None):
        req = urllib.request.Request(f"http://localhost:{PORT_OVERRIDE}{path}", data=body, method=method)
        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                return response.status, dict(response.getheaders()), response.read()
        except urllib.error.HTTPError as error:
            with error:
                return error.code, dict(error.headers), error.read()

    def test_servlet_path_is_overridden_via_application_yml(self):
        # The override path should work
        status, headers, body = self.request("GET", "/override/test?query=value")

        self.assertEqual(status, 201)
        self.assertEqual(headers.get("x-echo"), "1")
        self.assertEqual(json.loads(body), {"method": "GET", "sub_path": "/test", "query": {"query": "value"}})

    def test_default_path_is_not_available_after_override(self):
        # The default /echo path should not be available; we should get a 404
        status, _, _ = self.request("GET", "/echo/test")

        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
