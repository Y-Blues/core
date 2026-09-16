import inspect
import logging
import os
import sys
import unittest

import support  # noqa: F401
from support import TemporaryApplication, read_file, wait_until

from pelix.framework import Bundle
from pelix.ipopo.constants import use_ipopo

from ycappuccino.core import utils
from ycappuccino.core.component_factory import resolve_class
from ycappuccino.core.framework import Framework

APPLICATION = {
    "conf/application.yml": """
        name: demo
        bundle_prefix: PACKAGE
        layers:
          demo_on:
            active: true
          demo_off:
            active: false
        components:
          Greeter:
            prefix: Bonjour
        config:
          shell:
            console: false
          http_server:
            active: false
    """,
    "PACKAGE/__init__.py": "",
    "PACKAGE/services.py": """
        import typing
        from abc import ABC

        from ycappuccino.api.core import IActivityLogger
        from ycappuccino.api.core_base import (
            YCappuccinoComponent,
            YCappuccinoComponentBind,
            YCappuccinoType,
        )

        EVENTS = []
        COLLECTORS = []
        GALLERIES = []


        class IGreeter(YCappuccinoComponent, ABC):

            def greet(self, name):
                raise NotImplementedError


        class IMissing(YCappuccinoComponent, ABC):
            pass


        class Greeter(IGreeter):

            def __init__(
                self,
                logger: YCappuccinoType(IActivityLogger, "(name=main)"),
                prefix: str = "Hello",
            ):
                self._logger = logger
                self._prefix = prefix

            def greet(self, name):
                return f"{self._prefix} {name}"

            async def start(self):
                self._logger.info("greeter started")
                EVENTS.append("greeter.start")

            async def stop(self):
                EVENTS.append("greeter.stop")


        class Consumer(YCappuccinoComponent):

            def __init__(self, greeter: IGreeter, missing: typing.Optional[IMissing]):
                self._greeter = greeter
                self._missing = missing

            async def start(self):
                EVENTS.append(("consumer.start", self._greeter.greet("world"), self._missing))

            async def stop(self):
                EVENTS.append("consumer.stop")


        class Counter(YCappuccinoComponent):

            def __init__(self, count: int = 3):
                self.count = count

            async def start(self):
                pass

            async def stop(self):
                pass


        class Collector(YCappuccinoComponentBind):

            def __init__(self):
                super().__init__()
                self.greeters = []

            async def bind(self, a_service: IGreeter):
                self.greeters.append(a_service)

            async def un_bind(self, a_service: IGreeter):
                self.greeters.remove(a_service)

            async def start(self):
                COLLECTORS.append(self)

            async def stop(self):
                pass


        class Gallery(YCappuccinoComponent):

            def __init__(self, greeters: list[IGreeter], missing: list[IMissing]):
                self.greeters = greeters
                self.missing = missing

            async def start(self):
                GALLERIES.append(self)

            async def stop(self):
                pass
    """,
    "PACKAGE/legacy_on.py": """
        from pelix.ipopo.decorators import ComponentFactory, Instantiate, Provides
        from ycappuccino.core.decorator_app import Layer


        @ComponentFactory("PACKAGE-LegacyOn-Factory")
        @Provides("ILegacyOn")
        @Instantiate("PACKAGE-legacy-on")
        @Layer(name="demo_on")
        class LegacyOn(object):
            pass
    """,
    "PACKAGE/legacy_off.py": """
        from pelix.ipopo.decorators import ComponentFactory, Instantiate, Provides
        from ycappuccino.core.decorator_app import Layer


        @ComponentFactory("PACKAGE-LegacyOff-Factory")
        @Provides("ILegacyOff")
        @Instantiate("PACKAGE-legacy-off")
        @Layer(name="demo_off")
        class LegacyOff(object):
            pass
    """,
    "PACKAGE/extension/__init__.py": "",
    "PACKAGE/extension/legacy_dep.py": """
        from pelix.ipopo.decorators import ComponentFactory, Instantiate, Provides
        from ycappuccino.core.decorator_app import Layer


        @ComponentFactory("PACKAGE-LegacyDep-Factory")
        @Provides("ILegacyDep")
        @Instantiate("PACKAGE-legacy-dep")
        @Layer(name="demo_dep")
        class LegacyDep(object):
            pass
    """,
    "PACKAGE/extension/conf/config.yaml": """
        layer: demo_on
        dependencies_layer:
          demo_dep: true
          demo_off: false
    """,
    "PACKAGE/models.py": """
        from ycappuccino.api.decorators import Item
        from ycappuccino.api.models import Model


        @Item(collection="demos", name="PACKAGE_demo", plural="demos")
        class Demo(Model):
            pass
    """,
    "PACKAGE/broken.py": 'raise ImportError("this bundle is broken on purpose")\n',
    "PACKAGE/test_ignored.py": 'raise AssertionError("test modules must not be loaded")\n',
}


class TestFrameworkApplication(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = TemporaryApplication(APPLICATION).open()
        cls.addClassCleanup(cls.app.close)
        cls.framework = Framework()
        cls.framework.init(cls.app.yml_path)
        cls.addClassCleanup(cls.framework.stop)
        cls.context = cls.framework.ipopo.get_bundle_context()
        cls.services = cls.app.module("services")

    def get_service(self, specification, ldap_filter=None):
        reference = self.context.get_service_reference(specification, ldap_filter)
        self.assertIsNotNone(reference, specification)
        return self.context.get_service(reference)

    def test_native_component_is_started_with_its_dependencies(self):
        self.assertIn(("consumer.start", "Bonjour world", None), self.services.EVENTS)

    def test_property_values_keep_their_python_type(self):
        self.assertEqual(self.context.get_service_reference("Counter").get_property("count"), 3)

    def test_component_is_published_under_its_interfaces(self):
        self.assertEqual(self.get_service("IGreeter").greet("proxy"), "Bonjour proxy")

    def test_bind_receives_matching_services(self):
        collectors = wait_until(lambda: self.services.COLLECTORS)

        self.assertEqual([greeter.greet("x") for greeter in collectors[0].greeters], ["Bonjour x"])

    def test_list_parameter_receives_every_matching_service(self):
        galleries = wait_until(lambda: self.services.GALLERIES)

        self.assertEqual([greeter.greet("x") for greeter in galleries[0].greeters], ["Bonjour x"])
        self.assertEqual(galleries[0].missing, [])

    def test_core_bundles_are_started(self):
        self.get_service("IConfiguration")
        self.get_service("IActivityLogger", "(name=main)")
        self.get_service("IListComponent")

    def test_activity_logger_writes_in_the_application_data_directory(self):
        log_file = os.path.join(self.app.root, "data", "log", "Log-Activity-main.log")

        self.assertTrue(wait_until(lambda: "greeter started" in read_file(log_file)))

    def test_legacy_bundles_follow_active_layers(self):
        self.assertIsNotNone(self.context.get_service_reference("ILegacyOn"))
        self.assertIsNone(self.context.get_service_reference("ILegacyOff"))

    def test_layer_dependencies_are_activated(self):
        self.assertIsNotNone(self.context.get_service_reference("ILegacyDep"))

    def test_models_are_registered_with_their_file(self):
        models = self.app.module("models")

        self.assertEqual(self.framework.bundle_models_loaded_path_by_name[models.__name__], models.__file__)
        self.assertIs(self.framework.bundle_models_loaded_path_by_name, utils.bundle_models_loaded_path_by_name)

    def test_broken_and_test_modules_do_not_stop_the_framework(self):
        self.assertEqual(self.framework.ipopo.get_state(), Bundle.ACTIVE)
        self.assertNotIn(self.app.package + ".test_ignored", sys.modules)

    def test_factories_are_indexed_once_by_specification(self):
        self.assertEqual(
            self.framework.listener_factory.get_factories_by_service_specification("IGreeter"),
            [self.app.package + ".services.Greeter-Factory"],
        )

    def test_running_framework_is_the_singleton(self):
        self.assertIs(Framework.get_framework(), self.framework)
        self.assertIs(Framework.get_instance(), self.framework)

    def test_instantiate_component_publishes_a_new_service(self):
        handle = self.framework.instantiate_component(self.services.Greeter, {"prefix": "Yo"})
        self.addCleanup(self.framework.destroy_component, handle)

        greeter = self.get_service("IGreeter", "(prefix=Yo)")

        self.assertEqual(greeter.greet("there"), "Yo there")

    def test_instantiate_component_accepts_a_dotted_path(self):
        handle = self.framework.instantiate_component(
            self.app.package + ".services.Greeter", {"prefix": "Salut"}
        )
        self.addCleanup(self.framework.destroy_component, handle)

        greeter = self.get_service("IGreeter", "(prefix=Salut)")

        self.assertEqual(greeter.greet("there"), "Salut there")

    def test_instantiate_component_twice_creates_independent_instances(self):
        first = self.framework.instantiate_component(self.services.Greeter, {"prefix": "A"})
        self.addCleanup(self.framework.destroy_component, first)
        second = self.framework.instantiate_component(self.services.Greeter, {"prefix": "B"})
        self.addCleanup(self.framework.destroy_component, second)

        self.assertEqual(self.get_service("IGreeter", "(prefix=A)").greet("x"), "A x")
        self.assertEqual(self.get_service("IGreeter", "(prefix=B)").greet("x"), "B x")

    def test_destroy_component_stops_and_unpublishes_it(self):
        handle = self.framework.instantiate_component(self.services.Greeter, {"prefix": "Bye"})
        self.assertIsNotNone(self.context.get_service_reference("IGreeter", "(prefix=Bye)"))

        self.framework.destroy_component(handle)

        self.assertIsNone(self.context.get_service_reference("IGreeter", "(prefix=Bye)"))

    def test_destroy_component_is_idempotent(self):
        handle = self.framework.instantiate_component(self.services.Greeter, {"prefix": "Once"})

        self.framework.destroy_component(handle)
        self.framework.destroy_component(handle)  # must not raise

    def test_instantiate_component_rejects_a_non_component_class(self):
        with self.assertRaises(TypeError):
            self.framework.instantiate_component(object)

    def test_instantiate_component_rejects_an_unresolvable_dotted_path(self):
        with self.assertRaises(ImportError):
            self.framework.instantiate_component("no.such.module.NoSuchClass")

    def test_native_component_from_bundle_prefix_scan_is_listed(self):
        components = self.framework.list_components()
        by_class = {component["class"]: component for component in components}

        self.assertIn("Greeter", by_class)
        greeter = by_class["Greeter"]
        self.assertEqual(greeter["module"], self.services.__name__)
        self.assertIn(self.services.__name__ + ".IGreeter", greeter["provides"])
        self.assertIn(self.services.__name__ + ".Greeter", greeter["provides"])
        for qualified_path in greeter["provides"]:
            self.assertTrue(inspect.isclass(resolve_class(qualified_path)))

    def test_legacy_ipopo_bundle_is_not_listed(self):
        classes = {component["class"] for component in self.framework.list_components()}

        self.assertNotIn("LegacyOn", classes)

    def test_instantiate_component_adds_and_destroy_component_removes_the_listing(self):
        before = len(self.framework.list_components())

        handle = self.framework.instantiate_component(self.services.Greeter, {"prefix": "Listed"})
        components = self.framework.list_components()
        self.assertEqual(len(components), before + 1)
        listed = [component for component in components if component["module"] == self.services.__name__ and component["class"] == "Greeter"]
        self.assertTrue(any(self.services.__name__ + ".IGreeter" in component["provides"] for component in listed))

        self.framework.destroy_component(handle)

        self.assertEqual(len(self.framework.list_components()), before)


class TestFrameworkStartAndStop(unittest.TestCase):

    def test_startup_logs_no_error(self):
        app = TemporaryApplication(APPLICATION).open()
        self.addCleanup(app.close)
        framework = Framework()
        self.addCleanup(framework.stop)

        with self.assertNoLogs(level=logging.ERROR):
            framework.init(app.yml_path)

    def test_list_parameter_follows_services_leaving(self):
        app = TemporaryApplication(APPLICATION).open()
        self.addCleanup(app.close)
        framework = Framework()
        framework.init(app.yml_path)
        self.addCleanup(framework.stop)
        gallery = wait_until(lambda: app.module("services").GALLERIES)[0]

        with use_ipopo(framework.context) as ipopo:
            ipopo.kill(app.package + ".services.Greeter")

        self.assertTrue(wait_until(lambda: gallery.greeters == []))

    def test_stop_invalidates_native_components(self):
        app = TemporaryApplication(APPLICATION).open()
        self.addCleanup(app.close)
        framework = Framework()
        framework.init(app.yml_path)
        services = app.module("services")

        framework.stop()

        self.assertIn("consumer.stop", services.EVENTS)
        self.assertIn("greeter.stop", services.EVENTS)
        self.assertIsNot(Framework.get_framework(), framework)

    def test_stop_clears_the_component_listing(self):
        app = TemporaryApplication(APPLICATION).open()
        self.addCleanup(app.close)
        framework = Framework()
        framework.init(app.yml_path)
        self.assertNotEqual(framework.list_components(), [])

        framework.stop()

        self.assertEqual(framework.list_components(), [])

    def test_instantiate_component_requires_a_started_framework(self):
        with self.assertRaises(RuntimeError):
            Framework().instantiate_component(object)


class FakePelixFramework(object):

    def __init__(self, interrupt=False):
        self.calls = []
        self._interrupt = interrupt

    def wait_for_stop(self):
        self.calls.append("wait_for_stop")
        if self._interrupt:
            raise KeyboardInterrupt

    def start(self):
        self.calls.append("start")

    def stop(self):
        self.calls.append("stop")


class TestFrameworkLifecycle(unittest.TestCase):

    def test_start_blocks_until_the_framework_stops_without_restarting_it(self):
        framework = Framework()
        pelix_framework = framework.ipopo = FakePelixFramework()

        framework.start()

        self.assertEqual(pelix_framework.calls, ["wait_for_stop", "stop"])

    def test_keyboard_interrupt_stops_the_framework(self):
        framework = Framework()
        pelix_framework = framework.ipopo = FakePelixFramework(interrupt=True)

        framework.start()

        self.assertEqual(pelix_framework.calls, ["wait_for_stop", "stop"])


class TestFrameworkConfiguration(unittest.TestCase):

    def setUp(self):
        self.framework = Framework()
        self.framework.application_yaml = {
            "name": "demo",
            "bundle_prefix": "myapp",
            "layers": {
                "storage": {"active": True, "port": 27017},
                "disabled": {"active": False},
                "undeclared": {},
            },
            "config": {"http_server": {"active": True, "port": 8080, "ip": "localhost"}},
        }

    def test_active_layers(self):
        self.assertEqual(self.framework.get_layers(), ["storage"])

    def test_layer_properties(self):
        self.assertEqual(self.framework.get_layer_properties("storage")["port"], 27017)
        self.assertEqual(self.framework.get_layer_properties("unknown"), {})

    def test_bundle_prefix_accepts_a_string_or_a_list(self):
        self.assertEqual(self.framework.get_bundle_prefix(), ["myapp"])

        self.framework.application_yaml["bundle_prefix"] = ["myapp", "other"]
        self.assertEqual(self.framework.get_bundle_prefix(), ["myapp", "other"])

        del self.framework.application_yaml["bundle_prefix"]
        self.assertEqual(self.framework.get_bundle_prefix(), [])

    def test_http_server_settings(self):
        self.assertTrue(self.framework.is_http_server())
        self.assertEqual(self.framework.get_http_server_port(), 8080)
        self.assertEqual(self.framework.get_http_server_ip(), "localhost")
        self.assertEqual(self.framework.get_app_name(), "demo")


if __name__ == "__main__":
    unittest.main()
