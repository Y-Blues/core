import typing
import unittest
from abc import ABC

import support  # noqa: F401

from pelix.ipopo.constants import IPOPO_FACTORY_CONTEXT
from pelix.ipopo.decorators import ComponentFactory, Instantiate

from ycappuccino.api.core import IActivityLogger, IConfiguration
from ycappuccino.api.core_base import (
    YCappuccinoComponent,
    YCappuccinoComponentBind,
    YCappuccinoType,
)
from ycappuccino.api.http import HttpRequest, HttpResponse, IHttpServlet
from ycappuccino.api.proxy import YCappuccinoRemote
from ycappuccino.core.async_runner import AsyncRunner
from ycappuccino.core.component_factory import (
    Requirement,
    create_factory_module,
    describe_component,
    is_component,
    resolve_class,
)


class IHost(YCappuccinoRemote):
    """legacy-style interface: injectable because it derives from YCappuccinoRemote"""


class IGreeter(YCappuccinoComponent, ABC):

    def greet(self, name):
        raise NotImplementedError


class Lifecycle(object):

    async def start(self):
        pass

    async def stop(self):
        pass


class Greeter(Lifecycle, IGreeter):

    def __init__(
        self,
        logger: YCappuccinoType(IActivityLogger, "(name=main)"),
        prefix: str = "Hello",
    ):
        self.prefix = prefix


class Consumer(Lifecycle, YCappuccinoComponent):

    def __init__(
        self,
        greeter: IGreeter,
        config: typing.Optional[IConfiguration],
        manager: "IHost | None",
        fallback: IConfiguration = None,
    ):
        pass


class Settings(Lifecycle, YCappuccinoComponent):

    def __init__(self, count: int = 3, label="x"):
        pass


class Unresolvable(Lifecycle, YCappuccinoComponent):

    def __init__(self, name: str):
        pass


class Collector(Lifecycle, YCappuccinoComponentBind):

    async def bind(self, a_service: IGreeter):
        pass

    async def un_bind(self, a_service: IGreeter):
        pass


class Gallery(Lifecycle, YCappuccinoComponent):

    def __init__(
        self,
        greeters: list[IGreeter],
        loggers: list[YCappuccinoType(IActivityLogger, "(name=main)")],
    ):
        pass


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


class ManagedGreeter(Greeter, IHost):

    def __init__(self):
        IHost.__init__(self)


@ComponentFactory("LegacyGreeterFactory")
@Instantiate("legacy-greeter")
class LegacyGreeter(Lifecycle, IGreeter):
    pass


class TestIsComponent(unittest.TestCase):

    def test_concrete_component(self):
        self.assertTrue(is_component(Greeter))

    def test_abstract_interfaces(self):
        self.assertFalse(is_component(IGreeter))
        self.assertFalse(is_component(IConfiguration))

    def test_ycappuccino_type_marker(self):
        self.assertFalse(is_component(YCappuccinoType(Greeter, "(name=main)")))

    def test_plain_class(self):
        self.assertFalse(is_component(Lifecycle))

    def test_class_already_manipulated_by_ipopo(self):
        self.assertFalse(is_component(LegacyGreeter))


class TestDescribeComponent(unittest.TestCase):

    def test_names_are_qualified_by_module(self):
        description = describe_component(Greeter)

        self.assertEqual(description.name, __name__ + ".Greeter")
        self.assertEqual(description.factory_name, __name__ + ".Greeter-Factory")

    def test_interface_parameter_is_a_required_dependency(self):
        self.assertIn(
            Requirement("greeter", "IGreeter", optional=False, spec_filter=None),
            describe_component(Consumer).requires,
        )

    def test_ycappuccino_type_parameter_carries_its_filter(self):
        self.assertEqual(
            describe_component(Greeter).requires,
            [Requirement("logger", "IActivityLogger", optional=False, spec_filter="(name=main)")],
        )

    def test_optional_parameters_are_optional_dependencies(self):
        requires = {requirement.field: requirement for requirement in describe_component(Consumer).requires}

        for field, specification in (
            ("config", "IConfiguration"),
            ("manager", "IHost"),
            ("fallback", "IConfiguration"),
        ):
            with self.subTest(parameter=field):
                self.assertEqual(
                    requires[field],
                    Requirement(field, specification, optional=True, spec_filter=None),
                )

    def test_list_parameter_is_an_optional_aggregate_dependency(self):
        self.assertEqual(
            describe_component(Gallery).requires,
            [
                Requirement("greeters", "IGreeter", optional=True, spec_filter=None, aggregate=True),
                Requirement(
                    "loggers", "IActivityLogger", optional=True, spec_filter="(name=main)", aggregate=True
                ),
            ],
        )

    def test_parameters_with_default_values_are_properties(self):
        self.assertEqual(describe_component(Settings).properties, {"count": 3, "label": "x"})

    def test_parameter_that_cannot_be_injected_is_rejected(self):
        with self.assertRaisesRegex(TypeError, "'name'"):
            describe_component(Unresolvable)

    def test_component_is_provided_under_its_class_and_interfaces(self):
        self.assertEqual(describe_component(Greeter).provides, ["Greeter", "IGreeter"])

    def test_logger_component_does_not_provide_logging_classes(self):
        class FileLogger(Lifecycle, IActivityLogger):
            pass

        self.assertEqual(describe_component(FileLogger).provides, ["FileLogger", "IActivityLogger"])

    def test_remote_interfaces_are_provided(self):
        self.assertEqual(
            describe_component(ManagedGreeter).provides,
            ["ManagedGreeter", "Greeter", "IGreeter", "IHost", "YCappuccinoRemote"],
        )

    def test_provides_qualified_is_index_aligned_with_provides(self):
        description = describe_component(ManagedGreeter)

        self.assertEqual(description.provides, ["ManagedGreeter", "Greeter", "IGreeter", "IHost", "YCappuccinoRemote"])
        self.assertEqual(
            description.provides_qualified,
            [
                __name__ + ".ManagedGreeter",
                __name__ + ".Greeter",
                __name__ + ".IGreeter",
                __name__ + ".IHost",
                "ycappuccino.api.proxy.YCappuccinoRemote",
            ],
        )
        for short_name, qualified_path in zip(description.provides, description.provides_qualified):
            with self.subTest(specification=short_name):
                self.assertEqual(resolve_class(qualified_path).__name__, short_name)

    def test_bind_annotation_declares_an_aggregate_binding(self):
        self.assertEqual(
            [binding.specification for binding in describe_component(Collector).bindings],
            ["IGreeter"],
        )

    def test_http_servlet_provides_the_pelix_servlet_spec(self):
        self.assertEqual(
            describe_component(Servlet).provides,
            ["Servlet", "IHttpServlet", "pelix.http.servlet"],
        )

    def test_http_servlet_marker_is_mirrored_identically_in_provides_qualified(self):
        # "pelix.http.servlet" is a raw Pelix specification name, not a Python class: it has no
        # qualified path of its own, so it appears unchanged at the same index in both lists.
        description = describe_component(Servlet)

        self.assertEqual(description.provides[-1], "pelix.http.servlet")
        self.assertEqual(description.provides_qualified[-1], "pelix.http.servlet")
        self.assertEqual(len(description.provides), len(description.provides_qualified))

    def test_http_servlet_without_a_path_parameter_is_rejected(self):
        with self.assertRaises(TypeError):
            describe_component(ServletWithoutPath)


class TestCreateFactoryModule(unittest.TestCase):

    def setUp(self):
        self.runner = AsyncRunner()
        self.addCleanup(self.runner.shutdown)

    def test_non_servlet_components_do_not_have_getattribute_override(self):
        # Tripwire: non-servlet components should not get a __getattribute__ override
        # in their generated proxy class
        description = describe_component(Greeter)
        module = create_factory_module(description, self.runner, {})

        # Get the proxy class from the generated module
        proxy_class = getattr(module, "GreeterIpopoProxy")

        # Check that __getattribute__ is NOT in the proxy class's own namespace
        # (it may be inherited from Proxy, but not overridden)
        self.assertNotIn("__getattribute__", proxy_class.__dict__)

    def test_name_overrides_module_and_factory_identifiers(self):
        description = describe_component(Greeter)

        module = create_factory_module(description, self.runner, {}, name="custom-name")

        self.assertEqual(module.__name__, "custom-name_ipopo")
        proxy_class = getattr(module, "GreeterIpopoProxy")
        self.assertEqual(getattr(proxy_class, IPOPO_FACTORY_CONTEXT).name, "custom-name-Factory")

    def test_default_name_is_still_description_name(self):
        description = describe_component(Greeter)

        module = create_factory_module(description, self.runner, {})

        self.assertEqual(module.__name__, description.name + "_ipopo")


class TestResolveClass(unittest.TestCase):

    def test_resolves_a_dotted_path_to_its_class(self):
        self.assertIs(resolve_class(__name__ + ".Greeter"), Greeter)

    def test_rejects_a_path_without_a_module(self):
        with self.assertRaises(ValueError):
            resolve_class("Greeter")

    def test_unknown_module_raises_import_error(self):
        with self.assertRaises(ImportError):
            resolve_class("no.such.module.Greeter")

    def test_unknown_class_raises_import_error(self):
        with self.assertRaises(ImportError):
            resolve_class(__name__ + ".NoSuchClass")


if __name__ == "__main__":
    unittest.main()
