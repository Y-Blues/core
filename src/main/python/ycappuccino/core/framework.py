#!/usr/bin/env python
# -- Content-Encoding: UTF-8 --
"""
Class that allow to start the framework
"""
from __future__ import annotations

import logging
import re
import sys, importlib
import os
import time
from datetime import datetime
from importlib.abc import MetaPathFinder
from types import ModuleType
import inspect

import yaml

from ycappuccino.api.core.base import YCappuccinoComponentBind, YCappuccinoComponent
from ycappuccino.core.utils import MyLoader

sys.path.append(os.getcwd())
# Pelix
from pelix.framework import create_framework, BundleContext
from pelix.ipopo.constants import use_ipopo
import pelix.services

import glob


class MyMetaFinder(MetaPathFinder):

    def __init__(self, framework: Framework):
        super(MyMetaFinder).__init__()
        self._context = None
        self._init_bundles = []
        self.framework = framework

    def set_context(self, a_context):
        self._context = a_context
        for w_bundle in self._init_bundles:
            if ".api" in w_bundle["module"]:
                w_father_path = "/".join(w_bundle["path"].split("/")[0:-1])
                w_father_module = ".".join(w_bundle["module"].split(".")[0:-1])

                self.framework.find_and_install_bundle(
                    w_father_path, w_father_module, self._context
                )
            else:
                self.framework.find_and_install_bundle(
                    w_bundle["path"], w_bundle["module"], self._context
                )
        self._init_bundles = []


# ------------------------------------------------------------------------------

# Module version import syson
__version_info__ = (0, 1, 0)
__version__ = ".".join(str(x) for x in __version_info__)


_logger = logging.getLogger(__name__)

# ------------------------------------------------------------------------------


class ListenerFactories:
    def __init__(self, a_context):
        self._context = a_context
        self._factory_by_spec = {}
        with use_ipopo(self._context) as ipopo:
            ipopo.add_listener(self)
        self._notifier_by_spec = {}

    def handle_ipopo_event(self, event):
        """
        event: A IPopoEvent object
        """
        # ...
        with use_ipopo(self._context) as ipopo:
            w_description = ipopo.get_factory_details(event.get_factory_name())
            for w_service_spec in w_description["services"][0]:
                if w_service_spec not in self._factory_by_spec:
                    self._factory_by_spec[w_service_spec] = []
                self._factory_by_spec[w_service_spec].append(w_description["name"])
                if w_service_spec in self._notifier_by_spec:
                    for w_notifier in self._notifier_by_spec[w_service_spec]:
                        w_notifier.notify(w_description["name"])

    def subscribe_notifier(self, a_service_spec, a_notifier):
        if a_service_spec not in self._notifier_by_spec:
            self._notifier_by_spec[a_service_spec] = []
        self._notifier_by_spec[a_service_spec].append(a_notifier)

    def get_factories_by_service_specification(self, a_service_spec):
        if a_service_spec in self._factory_by_spec.keys():
            return self._factory_by_spec[a_service_spec]
        return []


class Framework:

    _singleton = None

    def __init__(self):

        self.item_manager = None
        self.context = None
        self.listener_factory = None
        # app config setted by init
        self.application_yaml = {}
        self.map_layer_class = {}
        self.map_app_class = {}
        self.bundle_loaded: list[str] = []
        self.ipopo = None
        self._finder = MyMetaFinder(self)
        self.bundle_models_loaded_path_by_name: dict = dict()
        sys.meta_path.insert(0, self._finder)

    @classmethod
    def get_framework(cls):
        if cls._singleton is None:
            cls._singleton = Framework()
        return cls._singleton

    def set_item_manager(self, a_item_manager):
        """set item manager"""
        self.item_manager = a_item_manager

    def add_app(self, obj_name: str, name: str) -> None:
        self.map_app_class[obj_name] = name

    def add_layer(self, obj_name: str, name: str) -> None:
        self.map_layer_class[obj_name] = name

    def is_http_server(self) -> bool:
        """return app paramaeter regarding yaml"""
        active = None
        if "config" in self.application_yaml.keys():
            if "http_server" in self.application_yaml["config"].keys():
                if "active" in self.application_yaml["config"]["http_server"].keys():
                    active = self.application_yaml["config"]["http_server"]["active"]
        return active

    def get_http_server_port(self):
        """return app paramaeter regarding yaml"""
        port = None
        if "config" in self.application_yaml.keys():
            if "http_server" in self.application_yaml["config"].keys():
                if "port" in self.application_yaml["config"]["http_server"].keys():
                    port = self.application_yaml["config"]["http_server"]["port"]
        return port

    def get_layer_properties(self, layer_name):
        """return port regarding yaml"""
        layers_properties = {}
        if "layers" in self.application_yaml.keys():
            if layer_name in self.application_yaml["layers"].keys():
                layers_properties = self.application_yaml["layers"][layer_name]
        return layers_properties

    def get_app_name(self):
        """return port regarding yaml"""
        app_name = None
        if "name" in self.application_yaml.keys():
            app_name = self.application_yaml["name"]
        return app_name

    def get_ip(self):
        """return port regarding yaml"""
        ip = None
        if "config" in self.application_yaml.keys():
            if "ip" in self.application_yaml["config"].keys():
                ip = self.application_yaml["config"]["ip"]
        return ip

    def get_bundle_prefix(self):
        """return port regarding yaml"""
        bundle_prefix = None
        if "bundle_prefix" in self.application_yaml.keys():
            bundle_prefix = self.application_yaml["bundle_prefix"]
        return bundle_prefix

    def get_model_app(self):
        """return app paramaeter regarding yaml"""

        app = []
        if "models.app" in self.application_yaml.keys():
            for elem in self.application_yaml["models.app"].keys():
                if self.application_yaml["models.app"][elem]:
                    app.append(elem)
        return app

    def get_layers(self):
        """return layers paramaeter regarding yaml"""

        layers = []
        if "layers" in self.application_yaml.keys():
            for elem in self.application_yaml["layers"].keys():
                if (
                    "active" in self.application_yaml["layers"][elem].keys()
                    and self.application_yaml["layers"][elem]["active"]
                ):
                    layers.append(elem)
        return layers

    def get_dependencies_layers(self, a_layer, a_list_layer=[]):
        """return dependencies layers  regarding yaml"""
        path = self.get_layer_path(a_layer)
        for file_path in glob.iglob(path + "/" + a_layer + "/conf/config*.yaml"):
            with open(file_path) as w_file:
                conf_yaml = yaml.safe_load(w_file)
                if "dependencies_layer" in conf_yaml.keys():
                    for elem in conf_yaml["dependencies_layer"].keys():
                        if (
                            conf_yaml["dependencies_layer"][elem]
                            and elem not in a_list_layer
                        ):
                            a_list_layer.append(elem)
                            self.get_dependencies_layers(elem, a_list_layer)
        return a_list_layer

    def get_layer_path(self, a_layer):
        """get the file path of the directory of the layer"""
        w_module = importlib.import_module(a_layer)
        return os.sep.join(w_module.__path__[0].split(os.sep)[0:-1])

    def init(self, yml_path):
        """ """

        with open(yml_path, "r") as file:
            self.application_yaml = yaml.safe_load(file)

        # Create the Pelix framework
        self.ipopo = create_framework(
            (
                # iPOPO
                "pelix.ipopo.core",
                # Shell ycappuccino_storage
                "pelix.shell.core",
                "pelix.shell.console",
                "pelix.shell.remote",
                "pelix.shell.ipopo",
                # ConfigurationAdmin
                "pelix.services.configadmin",
                "pelix.shell.configadmin",
                # EventAdmin,
                "pelix.services.eventadmin",
                "pelix.shell.eventadmin",
                "ycappuccino_api.core.api",
                "ycappuccino_core.bundles.configuration",
                "ycappuccino_core.bundles.activity_logger",
            )
        )

        # Start the framework
        self.ipopo.start()
        # Instantiate EventAdmin
        with use_ipopo(self.ipopo.get_bundle_context()) as ipopo:
            ipopo.instantiate(
                pelix.services.FACTORY_EVENT_ADMIN, "event-client_pyscript_core", {}
            )

        context = self.ipopo.get_bundle_context()

        # retrieve item_manager
        listener_factory = ListenerFactories(context)
        # install custom
        # load ycappuccino_storage
        w_root = ""
        root_dir = os.getcwd()
        for w_elem in root_dir.split("/"):
            if w_root == "":
                if os.sep == "\\":
                    w_root = w_root + w_elem
                else:
                    w_root = w_root + "/" + w_elem
            else:
                w_root = w_root + "/" + w_elem

        self.find_and_install_bundle(w_root, "", context)
        list_depend_layer = []
        for layer in self.get_layers():
            self.get_dependencies_layers(layer, list_depend_layer)
            self.find_and_install_bundle(self.get_layer_path(layer), "", context)

        for dep_layer in list_depend_layer:
            self.find_and_install_bundle(self.get_layer_path(dep_layer), "", context)

        # Install & start iPOPO
        context.install_bundle("pelix.ipopo.core").start()

        # Install & start the basic HTTP service
        context.install_bundle("pelix.http.basic").start()

        # Instantiate a HTTP service component
        if self.is_http_server():
            with use_ipopo(context) as ipopo:
                ipopo.instantiate(
                    "pelix.http.service.basic.factory",
                    "http-server",
                    {"pelix.http.port": self.get_http_server_port()},
                )

        self._finder.set_context(context)

        if self.item_manager is not None:
            self.item_manager.load_items()

    def start(self):

        try:
            self.ipopo.wait_for_stop()

            # Wait for the framework to stop
        except Exception:
            print("Interrupted by user, shutting down")
            self.ipopo.stop()
            sys.exit(0)

        self.ipopo.start()

    def get_requires_from_ycappuccino_component(
        self, component: type
    ) -> dict[str, list[list]]:
        sign = inspect.signature(component.__init__)
        binds: list[list] = []
        requires: list[list] = []

        if self.is_ycappuccino_component_bind(component):
            # manage type of bind to generate bind method
            sign_bind = inspect.signature(component.bind)
            for key, item in sign_bind.parameters.items():
                if key != "self":
                    if item.annotation.__name__ == "_UnionGenericAlias":
                        pass
                    else:
                        _tuple = [
                            item.annotation.__name__.lower(),
                            item.annotation.__name__,
                            True,
                            True,
                            "",
                            True,
                        ]

                        requires.append(_tuple)

                        elem = [
                            item.annotation.__name__.lower(),
                            item.annotation.__name__,
                        ]
                        binds.append(elem)

        properties: list[list] = []
        all: list[list] = []
        for key, item in sign.parameters.items():
            if item.default is not inspect._empty:
                elem = [key, item.annotation.__name__, item.default, False]
                properties.append(elem)
                all.append(elem)

            else:
                options = False
                spec_filter = ""
                _type = None
                require = False
                if type(item.annotation).__name__ == "_UnionGenericAlias":
                    options = True
                    if item.annotation.__args__[0].__name__ == "YCappuccinoTypeDefault":
                        spec_filter = item.annotation.__args__[0].spec_filter
                        _type = item.annotation.__args__[0].type.__name__
                    else:
                        _type = item.annotation.__arg__[0].__name__
                    require = True

                elif item.annotation.__name__ == "YCappuccinoTypeDefault":
                    spec_filter = item.annotation.spec_filter
                    _type = item.annotation.type.__name__
                    require = True
                elif self.is_ycappuccino_component(item.annotation, True):
                    _type = item.annotation.__name__
                    require = True

                if _type:
                    _tuple = [
                        key,
                        _type,
                        False,
                        options,
                        spec_filter,
                        require,
                    ]
                    requires.append(_tuple)
                    all.append(_tuple)
        return {
            "requires": requires,
            "properties": properties,
            "binds": binds,
            "all": all,
            "requires_spec": [require[1] for require in requires],
            "binds_spec": [bind[1] for bind in binds],
        }

    def is_ycappuccino_component(
        self, a_klass: type, include_pelix: bool = False, inpect=None
    ) -> bool:
        first = True
        for supertype in a_klass.__mro__:
            if supertype is not inspect._empty:
                if supertype.__name__ == YCappuccinoComponent.__name__:
                    if first:
                        return False
                    else:
                        return True
                elif include_pelix and a_klass is not inspect._empty:
                    list_subclass = supertype.__subclasses__()
                    for subclass in list_subclass:
                        if hasattr(subclass, "_ipopo_property_getter"):
                            return True

            first = False
        return False

    def is_ycappuccino_component_bind(
        self, a_klass: type, include_pelix: bool = False
    ) -> bool:
        first = True
        for supertype in a_klass.__mro__:
            if supertype is not inspect._empty:
                if supertype.__name__ == YCappuccinoComponentBind.__name__:
                    if first:
                        return False
                    else:
                        return True
                elif include_pelix and a_klass is not inspect._empty:
                    list_subclass = supertype.__subclasses__()
                    for subclass in list_subclass:
                        if hasattr(subclass, "_ipopo_property_getter"):
                            return True

            first = False
        return False

    def get_dumps(
        self, kind: str, dec_tuple: list[list], parameter_dump: list[str] = []
    ) -> list[str]:
        if dec_tuple is None:
            return []
        properties_dump: list[str] = []
        for property in dec_tuple:
            if property[-1]:
                properties_dump.append(
                    f'@{kind}("{property[0]}", "{property[1]}", optional={property[2]},aggregate={property[3]}, spec_filter="{property[4]}")'
                )
            else:
                if kind == "Property":
                    properties_dump.append(
                        f'@{kind}("{property[0]}","{property[0]}","{property[2]}")'
                    )
                else:
                    properties_dump.append(f'@{kind}("{property[0]}","{property[1]}")')
            parameter_dump.append(f"self.{property[0]} = None")

        return properties_dump

    def get_bind_dumps(
        self, kind: str, dec_tuple: list[list], parameter_dump: list[str] = []
    ) -> list[str]:
        if dec_tuple is None:
            return []
        properties_dump: list[str] = []
        for property in dec_tuple:
            properties_dump.append(
                f"""
    @BindField("{property[0]}")
    def bind_{property[0]}(self, field, service, service_ref):
        asyncio.run(self._obj.bind(service))
        
    @UnbindField("{property[0]}")
    def un_bind_{property[0]}(self, field, service, service_ref):
        asyncio.run(self._obj.un_bind(service))

"""
            )

        return properties_dump

    def get_arg_new(self, all: list[list]) -> list[str]:
        args_new: list[str] = []
        for property in all:
            if property[-1]:
                prop = f"None if self.{property[0]} is None else  self.{property[0]}[0]._obj if  isinstance(self.{property[0]},list) else self.{property[0]}._obj"
            else:
                prop = f"self.{property[0]}"

            args_new.append(prop)
        return args_new

    def get_ycappuccino_klass(self, module: ModuleType) -> list[type]:
        return [
            klass
            for name, klass in inspect.getmembers(module, inspect.isclass)
            if inspect.isclass(klass)
        ]

    def get_ycappuccino_component(self, module: ModuleType) -> list[type]:
        list_klass: list[type] = [
            klass
            for name, klass in inspect.getmembers(module, inspect.isclass)
            if inspect.isclass(klass)
        ]
        # get  class is YCappuccinoComponent
        list_ycappuccino_component: list[type] = [
            klass for klass in list_klass if self.is_ycappuccino_component(klass)
        ]
        return list_ycappuccino_component

    def load_bundle_ycappuccino(
        self,
        module: ModuleType,
        a_path: str,
        a_module_name: str,
        a_context: BundleContext,
    ):
        """
        analyse the file and create a new bundle dynamically regarding the ycappuccino component to create a proxy ipopo component
        :param installed_bundle:
        :param a_path:
        :param a_module_name:
        :param a_context:
        :return:
        """

        pelix_module_father = ".".join(a_module_name.split(".")[:-1])

        pelix_module = (
            pelix_module_father + "." + a_module_name.split(".")[-1] + "_pelix"
        )
        # get module
        # check if the class admit
        # get all class in module

        # get  class is YCappuccinoComponent
        list_ycappuccino_component = self.get_ycappuccino_component(module)
        with open(a_path, "r") as f:
            content_original_file = f.readlines()

        content = ""
        for ycappuccino_component in list_ycappuccino_component:
            # ensure to create only the classes implemented
            list_matches = re.findall(
                f"class {ycappuccino_component.__name__}.*",
                "\n".join(content_original_file),
            )
            if list_matches is not None and len(list_matches) > 0:
                props = self.get_requires_from_ycappuccino_component(
                    ycappuccino_component
                )

                factory: str = ycappuccino_component.__name__ + "Factory"
                provides: str = '","'.join(
                    [
                        comp.__name__
                        for comp in list_ycappuccino_component
                        if comp.__name__ not in props.get("requires_spec")
                        and comp.__name__ not in props.get("binds_spec")
                    ]
                )
                parameters: list[str] = []
                args_new: list[str] = self.get_arg_new(props.get("all"))
                properties: list[str] = self.get_dumps(
                    kind="Property",
                    parameter_dump=parameters,
                    dec_tuple=props.get("properties"),
                )
                requires: list[str] = self.get_dumps(
                    kind="Requires",
                    parameter_dump=parameters,
                    dec_tuple=props.get("requires"),
                )
                bind_methods: list[str] = self.get_bind_dumps(
                    kind="BindField",
                    parameter_dump=parameters,
                    dec_tuple=props.get("binds"),
                )
                bind_methods_dump: str = "\n".join(bind_methods)
                requires_dump: str = "\n".join(requires)
                properties_dump: str = "\n".join(properties)
                parameter_dump: str = "\n        ".join(parameters)
                instance: str = "_".join([factory, str(datetime.now().timestamp())])
                args_new_dump = ",".join(args_new)
                class_new: str = f"{ycappuccino_component.__name__}({args_new_dump})"
                klass: str = ycappuccino_component.__name__
                content = (
                    content
                    + f"""\n
from pelix.ipopo.decorators import  BindField, UnbindField,Instantiate, Requires, Provides, ComponentFactory, Property, Validate, Invalidate
import asyncio
from ycappuccino_api.proxy.api import Proxy
from {module.__name__} import {klass}


@ComponentFactory("{factory}")
@Provides(specifications=["{provides}"])
{requires_dump}
{properties_dump}
@Instantiate("{instance}")
class {factory}Ipopo(Proxy):

    def __int__(self):
        super().__init__()
        self._context = None
        {parameter_dump}

    {bind_methods_dump}

    @Validate
    def validate(self, context):
        self._objname = "{instance}"
        self._obj = {class_new}
        self._obj._ipopo = self
        self._context = context
        asyncio.run(self._obj.start())
        
    @Invalidate
    def in_validate(self, context):
        asyncio.run(self._obj.stop())
        self._objname = None
        self._obj = None
        self._context = None
"""
                )

        # with open(f"{a_path}".replace(".py", "_pelix") + ".py", "w") as f:
        #     f.write(content)
        mymodule = ModuleType(pelix_module)
        exec(content, mymodule.__dict__)
        sys.modules[pelix_module] = mymodule
        a_context.install_bundle(pelix_module).start()

    def load_bundle_pelix(
        self, a_path: str, content: str, a_module_name: str, a_context: BundleContext
    ) -> None:

        if self.get_layers() is None:
            a_context.install_bundle(a_module_name).start()
        else:
            # load layer regarding app layer to load
            w_layer_patterns = self.get_layers()
            for layer in self.get_layers():
                w_layer_patterns.extend(self.get_dependencies_layers(layer))

            for w_layer_pattern in w_layer_patterns:
                w_layer_pattern_1 = (
                    '@Layer\(name="' + w_layer_pattern.replace("*", ".*") + '"\)'
                )
                w_layer_pattern_2 = (
                    "@Layer\(name='" + w_layer_pattern.replace("*", ".*") + '"\)'
                )
                if re.search(w_layer_pattern_1, content) or re.search(
                    w_layer_pattern_2, content
                ):
                    print("{} : load {}".format(time.time(), a_module_name))
                    a_context.install_bundle(a_module_name).start()
                    return

            if (
                "@Layer(name=" not in content
                or "ycappuccino_storage/ycappuccino_core/utils" in a_path
            ):
                a_context.install_bundle(a_module_name).start()
                return

    def load_bundle_model_ycappuccino(self, a_path, content, a_module_name):
        if (
            a_module_name == "ycappuccino_core.models.decorators"
            or a_module_name == "ycappuccino_core.models.utils"
            or a_module_name == "ycappuccino_core.decorator_app"
        ):
            self.add_bundle_model(a_module_name, a_path)
        if "@Item" in content:
            # load module define for an app
            if self.get_app_name() is None:
                return self.add_bundle_model(a_module_name, a_path)
            else:
                for app_name in self.get_app_name():
                    w_app_pattern_applyed = '@App\(name="' + app_name.replace("*", ".*")
                    w_app_pattern_applyed_2 = "@App\(name='" + app_name.replace(
                        "*", ".*"
                    )
                    if re.search(w_app_pattern_applyed, content) or re.search(
                        w_app_pattern_applyed_2, content
                    ):
                        return self.add_bundle_model(a_module_name, a_path)

            if (
                "@App(name=" not in content
                or "ycappuccino_storage/ycappuccino_core/utils" in a_path
            ):
                return self.add_bundle_model(a_module_name, a_path)

    def load_bundle(self, a_path, a_module_name, a_context):
        """return list of models to load . need to be load after component"""
        try:
            if "/" in a_path and not a_path.split("/")[-1].startswith("test_"):

                with open(a_path, "r") as f:
                    content = f.read()
                    if a_module_name not in self.bundle_loaded and "class" in content:

                        self.bundle_loaded.append(a_module_name)
                        if (
                            "pelix" not in a_module_name
                            and "@ComponentFactory" in content
                            and "pelix.ipopo.decorators" in content
                        ):
                            self.load_bundle_pelix(
                                a_path, content, a_module_name, a_context
                            )
                        else:
                            if "__init__" in a_module_name or ".setup" in a_module_name:
                                return
                            installed_bundle = a_context.install_bundle(
                                a_module_name, a_path
                            )
                            installed_bundle.start()
                            module = installed_bundle.get_module()
                            if len(self.get_ycappuccino_component(module)) > 0:
                                self.load_bundle_ycappuccino(
                                    module,
                                    a_path,
                                    a_module_name,
                                    a_context,
                                )
                            else:
                                self.load_bundle_model_ycappuccino(
                                    a_path, content, a_module_name
                                )

        except Exception as e:
            _logger.exception("fail to load bundle {}".format(repr(e)))

    def add_bundle_model(self, a_module_name, a_file, a_cumul=False):
        if (
            not a_cumul
            and a_module_name not in self.bundle_models_loaded_path_by_name.keys()
        ):
            self.bundle_models_loaded_path_by_name[a_module_name] = a_file
            return a_module_name

    def find_and_install_bundle(self, a_root, a_module_name, a_context):
        """find and install all bundle in path"""
        w_list_model = []
        prefix_ok = False
        for prefix in self.get_bundle_prefix():
            prefix_ok = prefix in a_root
            if prefix_ok:
                break

        if not prefix_ok:
            return
        for w_file in glob.iglob(a_root + "/*"):
            w_file = w_file.replace(os.sep, "/")
            if "/" in w_file and not w_file.split("/")[-1].startswith("test_"):

                if (
                    os.path.exists(w_file)
                    and "pelix" not in w_file
                    and "pelix" not in a_module_name
                    and "framework" not in w_file
                ):
                    w_module_name = ""

                    if os.path.isdir(w_file) and os.path.isfile(
                        w_file + "/__init__.py"
                    ):
                        if a_module_name == "":
                            w_module_name = w_file.split("/")[-1]

                        else:
                            w_module_name = a_module_name + "." + w_file.split("/")[-1]
                        self.find_and_install_bundle(w_file, w_module_name, a_context)
                    elif os.path.isfile(w_file) and w_file.endswith(".py"):
                        w_module_name = a_module_name + "." + w_file.split("/")[-1][:-3]
                        if w_module_name not in self.bundle_loaded:
                            w_model = self.load_bundle(w_file, w_module_name, a_context)
                            if w_model is not None:
                                w_list_model.append(w_model)

            # load models at the end of all component
            for w_model in w_list_model:
                a_context.install_bundle(w_model)

    def find_spec(self, fullname, path, target=None):
        if path is not None:
            w_path = path[0]
            w_filename = fullname.split(".")[-1]
            w_fullpath = "{}/{}.py".format(w_path, w_filename)
            if not os.path.isfile(w_fullpath):
                w_fullpath = w_path + "/" + w_filename

            if self._context:
                if fullname not in self.get_bundle_loaded():
                    if ".api" in w_fullpath:
                        w_father_fullpath = w_fullpath.split("/")[0:-1]
                        self.framework.find_and_install_bundle(
                            w_father_fullpath, "", self._context
                        )
                    else:
                        self.framework.find_and_install_bundle(
                            w_fullpath, fullname, self._context
                        )

            elif "pelix" not in w_fullpath and "ycappuccino_core" not in w_fullpath:
                w_module = {"path": w_fullpath, "module": fullname}
                self._init_bundles.append(w_module)
        if path is None or path == "":
            # find first if a packages is named finish by module name

            path = [os.getcwd()]  # top level import --
            if "." in fullname:
                *parents, name = fullname.split(".")
            else:
                name = fullname

            for entry in path:
                if os.path.isdir(os.path.join(entry, name)):
                    # this module has child modules
                    filename = os.path.join(entry, name, "__init__.py")
                    submodule_locations = [os.path.join(entry, name)]
                else:
                    filename = os.path.join(entry, name + ".py")
                    submodule_locations = None
                if not os.path.exists(filename):
                    continue

                return self.spec_from_file_location(
                    fullname,
                    filename,
                    loader=MyLoader(filename),
                    submodule_search_locations=submodule_locations,
                )

            return None  # we don't know how to import this
