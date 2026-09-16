#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
YCappuccino framework: reads application.yml, starts Pelix/iPOPO and loads the bundles
found in the scanned packages (the core bundles and the packages listed in bundle_prefix).

For every module of those packages:

- classes manipulated by the iPOPO decorators (legacy bundles) get their module installed
  as a Pelix bundle,
- concrete YCappuccinoComponent subclasses get a generated iPOPO factory and instance
  (see ycappuccino.core.component_factory),
- modules declaring @Item models are registered in bundle_models_loaded_path_by_name.

A class decorated with @Layer(name=...) is only loaded when its layer is active: declared
active in application.yml, or a dependency of an active layer. A package declares the
dependencies of its layer in conf/config*.yaml::

    layer: ycappuccino_storage        # default: package name with "." replaced by "_"
    dependencies_layer:
      ycappuccino_core: true
"""

import dataclasses
import fnmatch
import glob
import importlib
import inspect
import itertools
import logging
import os
import pkgutil
import sys
from typing import Optional, Union

import pelix.services  # type: ignore
import yaml
from pelix.framework import Bundle, FrameworkFactory, create_framework  # type: ignore
from pelix.http import FACTORY_HTTP_BASIC, HTTP_SERVICE_ADDRESS, HTTP_SERVICE_PORT  # type: ignore
from pelix.ipopo.constants import IPopoEvent, use_ipopo  # type: ignore

from ycappuccino.api import decorators as model_decorators
from ycappuccino.core import utils
from ycappuccino.core.async_runner import AsyncRunner
from ycappuccino.core.component_factory import (
    ComponentDescription,
    create_factory_module,
    describe_component,
    is_component,
    is_ipopo_component,
    resolve_class,
)

_logger = logging.getLogger(__name__)

CORE_BUNDLES_PACKAGE = "ycappuccino.core.bundles"

# ConfigAdmin is not started: its file persistence reads conf/, where application.yml lives
_PELIX_BUNDLES = (
    "pelix.ipopo.core",
    "pelix.shell.core",
    "pelix.shell.ipopo",
    "pelix.services.eventadmin",
    "pelix.shell.eventadmin",
)

DEFAULT_HTTP_PORT = 8080


@dataclasses.dataclass(frozen=True)
class ComponentHandle:
    """returned by Framework.instantiate_component, to pass to destroy_component"""

    bundle: Bundle
    module_name: str
    component_name: str


class ListenerFactories:
    """index the iPOPO factories by provided specification and notify subscribers of new factories"""

    def __init__(self, a_context):
        self._context = a_context
        self._factory_by_spec = {}
        self._notifier_by_spec = {}
        with use_ipopo(self._context) as ipopo:
            ipopo.add_listener(self)

    def handle_ipopo_event(self, event):
        """
        event: A IPopoEvent object
        """
        w_factory_name = event.get_factory_name()
        if event.get_kind() == IPopoEvent.REGISTERED:
            with use_ipopo(self._context) as ipopo:
                w_description = ipopo.get_factory_details(w_factory_name)
            for w_specifications in w_description.get("services", []):
                for w_service_spec in w_specifications:
                    self._factory_by_spec.setdefault(w_service_spec, []).append(w_factory_name)
                    for w_notifier in self._notifier_by_spec.get(w_service_spec, []):
                        w_notifier.notify(w_factory_name)
        elif event.get_kind() == IPopoEvent.UNREGISTERED:
            for w_factories in self._factory_by_spec.values():
                while w_factory_name in w_factories:
                    w_factories.remove(w_factory_name)

    def subscribe_notifier(self, a_service_spec, a_notifier):
        self._notifier_by_spec.setdefault(a_service_spec, []).append(a_notifier)

    def get_factories_by_service_specification(self, a_service_spec):
        return list(self._factory_by_spec.get(a_service_spec, []))


class Framework:

    _singleton = None

    def __init__(self):
        self.item_manager = None
        self.context = None
        self.listener_factory = None
        # Pelix framework, created by init
        self.ipopo = None
        # app config setted by init
        self.application_yaml = {}
        self.map_layer_class = utils.map_layer_class
        self.map_app_class = utils.map_app_class
        self.bundle_models_loaded_path_by_name = utils.bundle_models_loaded_path_by_name
        # layer -> layers it depends on, read from the conf/config*.yaml of the scanned packages
        self._layer_dependencies = {}
        self._async_runner = AsyncRunner()
        self._component_sequence = itertools.count(1)
        # native components currently installed, by their unique instance name (the same
        # identity used to name their Pelix instance/factory: "module.Class" for a component
        # found by load_bundles()'s bundle_prefix scan, "module.Class#N" for one created at
        # runtime by instantiate_component) - see list_components()
        self._components: dict[str, ComponentDescription] = {}

    @classmethod
    def get_framework(cls):
        if cls._singleton is None:
            cls._singleton = Framework()
        return cls._singleton

    @classmethod
    def get_instance(cls):
        """alias of get_framework"""
        return cls.get_framework()

    def set_item_manager(self, a_item_manager):
        """set item manager"""
        self.item_manager = a_item_manager

    def add_app(self, obj_name: str, name: str) -> None:
        self.map_app_class[obj_name] = name

    def add_layer(self, obj_name: str, name: str) -> None:
        self.map_layer_class[obj_name] = name

    # ------------------------------------------------------------------ application.yml

    def _config(self) -> dict:
        return self.application_yaml.get("config") or {}

    def _http_server_config(self) -> dict:
        return self._config().get("http_server") or {}

    def is_http_server(self) -> bool:
        return bool(self._http_server_config().get("active", False))

    def get_http_server_port(self):
        return self._http_server_config().get("port")

    def get_http_server_ip(self):
        return self._http_server_config().get("ip", self.get_ip())

    def get_ip(self):
        return self._config().get("ip")

    def is_shell_console(self) -> bool:
        """interactive Pelix shell: config.shell.console, by default only when stdin is a terminal"""
        shell = self._config().get("shell") or {}
        if "console" in shell:
            return bool(shell["console"])
        try:
            return sys.stdin is not None and sys.stdin.isatty()
        except ValueError:
            return False

    def get_layer_properties(self, layer_name) -> dict:
        return (self.application_yaml.get("layers") or {}).get(layer_name) or {}

    def get_app_name(self):
        return self.application_yaml.get("name")

    def get_bundle_prefix(self) -> list:
        """packages to scan for bundles"""
        prefix = self.application_yaml.get("bundle_prefix")
        if prefix is None:
            return []
        if isinstance(prefix, str):
            return [prefix]
        return list(prefix)

    def get_model_app(self) -> list:
        models_app = self.application_yaml.get("models.app") or {}
        return [app for app, enabled in models_app.items() if enabled]

    def get_layers(self) -> list:
        """layers declared active in application.yml"""
        layers = self.application_yaml.get("layers") or {}
        return [layer for layer, properties in layers.items() if (properties or {}).get("active")]

    def get_active_layers(self) -> set:
        """active layers and, transitively, the layers they depend on"""
        active = set()
        pending = list(self.get_layers())
        while pending:
            layer = pending.pop()
            if layer not in active:
                active.add(layer)
                pending.extend(self._layer_dependencies.get(layer, ()))
        return active

    # ------------------------------------------------------------------ lifecycle

    def init(self, yml_path):
        """read the application configuration, start Pelix and load the bundles"""
        with open(yml_path, "r") as file:
            self.application_yaml = yaml.safe_load(file) or {}
        Framework._singleton = self

        # application modules are importable from the working directory
        if os.getcwd() not in sys.path:
            sys.path.append(os.getcwd())

        bundles = list(_PELIX_BUNDLES)
        if self.is_shell_console():
            bundles.append("pelix.shell.console")
        if self.is_http_server():
            bundles.append("pelix.http.basic")

        self.ipopo = create_framework(bundles)
        self.ipopo.start()
        self.context = self.ipopo.get_bundle_context()

        with use_ipopo(self.context) as ipopo:
            ipopo.instantiate(pelix.services.FACTORY_EVENT_ADMIN, "event-client_pyscript_core", {})
            if self.is_http_server():
                properties = {HTTP_SERVICE_PORT: self.get_http_server_port() or DEFAULT_HTTP_PORT}
                if self.get_http_server_ip():
                    properties[HTTP_SERVICE_ADDRESS] = self.get_http_server_ip()
                ipopo.instantiate(FACTORY_HTTP_BASIC, "http-server", properties)

        self.listener_factory = ListenerFactories(self.context)
        self.load_bundles()

        if self.item_manager is not None:
            self.item_manager.load_items()

    def start(self):
        """block until the framework stops; Ctrl+C stops it"""
        try:
            self.ipopo.wait_for_stop()
        except KeyboardInterrupt:
            _logger.info("Interrupted by user, shutting down")
        finally:
            self.stop()

    def stop(self):
        """stop Pelix, which invalidates every component, and release the framework"""
        if self.ipopo is not None:
            self.ipopo.stop()
            FrameworkFactory.delete_framework(self.ipopo)
            self.ipopo = None
            self.context = None
        self._async_runner.shutdown()
        self._components.clear()
        if Framework._singleton is self:
            Framework._singleton = None

    # ------------------------------------------------------------------ bundles

    def load_bundles(self):
        """import the modules of the scanned packages and install what they declare"""
        modules = self._import_modules([CORE_BUNDLES_PACKAGE] + self.get_bundle_prefix())
        active_layers = self.get_active_layers()
        for module in modules:
            try:
                self._install_module(module, active_layers)
            except Exception:
                _logger.exception("fail to load bundle %s", module.__name__)

    def add_bundle_model(self, a_module_name, a_file):
        self.bundle_models_loaded_path_by_name.setdefault(a_module_name, a_file)
        return a_module_name

    def _import_modules(self, package_names) -> list:
        modules = {}
        for package_name in package_names:
            for module_name in self._module_names(package_name):
                if module_name in modules:
                    continue
                try:
                    modules[module_name] = importlib.import_module(module_name)
                except Exception as error:
                    _logger.warning("fail to import bundle %s: %r", module_name, error)
                    _logger.debug("import error of bundle %s", module_name, exc_info=True)
        return list(modules.values())

    def _module_names(self, package_name) -> list:
        """the package and all its modules, test modules excepted"""
        try:
            package = importlib.import_module(package_name)
        except Exception as error:
            _logger.warning("fail to import package %s: %r", package_name, error)
            return []

        names = [package_name]
        if not hasattr(package, "__path__"):
            return names

        self._read_layer_configuration(package)
        for module_info in pkgutil.walk_packages(
            package.__path__, package_name + ".", onerror=_log_walk_error
        ):
            if _is_test_module(module_info.name):
                continue
            names.append(module_info.name)
            if module_info.ispkg:
                try:
                    self._read_layer_configuration(importlib.import_module(module_info.name))
                except Exception as error:
                    _logger.warning("fail to import package %s: %r", module_info.name, error)
        return names

    def _read_layer_configuration(self, package):
        for path in list(package.__path__):
            for file_path in sorted(glob.glob(os.path.join(path, "conf", "config*.yaml"))):
                try:
                    with open(file_path) as file:
                        configuration = yaml.safe_load(file) or {}
                except (OSError, yaml.YAMLError) as error:
                    _logger.warning("fail to read layer configuration %s: %r", file_path, error)
                    continue
                layer = configuration.get("layer", package.__name__.replace(".", "_"))
                dependencies = configuration.get("dependencies_layer") or {}
                self._layer_dependencies.setdefault(layer, set()).update(
                    name for name, enabled in dependencies.items() if enabled
                )

    def _install_module(self, module, active_layers):
        classes = [
            klass
            for _, klass in inspect.getmembers(module, inspect.isclass)
            if klass.__module__ == module.__name__
        ]
        enabled = [klass for klass in classes if _is_layer_active(klass, active_layers)]

        if any(is_ipopo_component(klass) for klass in enabled):
            self.context.install_bundle(module.__name__).start()

        for klass in enabled:
            if is_component(klass):
                try:
                    self._install_component(klass)
                except Exception:
                    _logger.exception(
                        "fail to create component %s.%s", module.__name__, klass.__qualname__
                    )

        if any(_is_model(klass) for klass in classes):
            self.add_bundle_model(module.__name__, module.__file__)

    def _install_component(self, klass):
        description = describe_component(klass)
        module = create_factory_module(
            description, self._async_runner, self._component_properties(description)
        )
        sys.modules[module.__name__] = module
        self.context.install_bundle(module.__name__).start()
        self._components[description.name] = description

    def _component_properties(self, description) -> dict:
        """properties of a component set in application.yml, by class name or qualified name"""
        components = self.application_yaml.get("components") or {}
        properties = dict(components.get(description.component.__name__) or {})
        properties.update(components.get(description.name) or {})
        return properties

    # ------------------------------------------------------------------ runtime components

    def instantiate_component(
        self, component: Union[type, str], properties: Optional[dict] = None
    ) -> ComponentHandle:
        """
        Install and start one native component instance outside of load_bundles()'s one-time
        startup scan. `component` is a concrete YCappuccinoComponent subclass, or a dotted
        "module.ClassName" path to one; `properties` overrides its constructor properties,
        exactly like `components: <name>: {...}` in application.yml. Returns a handle to give
        to destroy_component() to stop and uninstall it later. The framework must be started
        (init()) first; every call creates an independent instance, even for the same class.
        """
        if self.context is None:
            raise RuntimeError("instantiate_component requires a started framework")
        klass = resolve_class(component) if isinstance(component, str) else component
        if not is_component(klass):
            raise TypeError(f"{klass!r} is not a native YCappuccino component")

        description = describe_component(klass)
        name = f"{description.name}#{next(self._component_sequence)}"
        module = create_factory_module(description, self._async_runner, properties, name=name)
        sys.modules[module.__name__] = module
        bundle = self.context.install_bundle(module.__name__)
        try:
            bundle.start()
        except Exception:
            sys.modules.pop(module.__name__, None)
            raise
        self._components[name] = description
        return ComponentHandle(bundle, module.__name__, name)

    def destroy_component(self, handle: ComponentHandle) -> None:
        """stop and uninstall a component created by instantiate_component; a no-op if it was
        already destroyed"""
        if handle.bundle.get_state() != Bundle.UNINSTALLED:
            handle.bundle.uninstall()
        sys.modules.pop(handle.module_name, None)
        self._components.pop(handle.component_name, None)

    def list_components(self) -> list:
        """
        Every native component currently installed in this Framework instance: its own module,
        class name, and the fully-qualified dotted path of every specification it provides
        (resolve any of these with ycappuccino.core.component_factory.resolve_class). One entry
        per installed component, native components created via instantiate_component() included;
        legacy iPOPO-bundle components (installed via @ComponentFactory, not through
        describe_component) are not included - see README, "Installer un composant à l'exécution".

        [{"module": "myapp.greeting", "class": "Greeter", "provides": ["myapp.greeting.IGreeter"]}]
        """
        return [
            {
                "module": description.component.__module__,
                "class": description.component.__qualname__,
                "provides": list(description.provides_qualified),
            }
            for description in self._components.values()
        ]


def _is_test_module(module_name) -> bool:
    parts = module_name.split(".")
    return (
        parts[-1].startswith("test_")
        or parts[-1] in ("setup", "__main__")
        or any(part in ("test", "tests") for part in parts)
    )


def _is_layer_active(klass, active_layers) -> bool:
    layer = getattr(klass, utils.LAYER_ATTRIBUTE, None)
    return layer is None or any(fnmatch.fnmatchcase(layer, pattern) for pattern in active_layers)


def _is_model(klass) -> bool:
    return any(
        item.get("_class_obj") is klass for item in model_decorators.map_item_by_class.values()
    )


def _log_walk_error(package_name):
    _logger.warning("fail to import package %s", package_name)
