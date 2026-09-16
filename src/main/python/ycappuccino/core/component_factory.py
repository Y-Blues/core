"""
Turns YCappuccino components into iPOPO components (Spring-like constructor injection).

A component is a concrete subclass of YCappuccinoComponent. Its constructor declares its wiring:

- a parameter typed with a component interface, or with YCappuccinoType(IFace, "(ldap=filter)"),
  is a dependency. It is optional when typed Optional[IFace] / IFace | None or defaulting to None;
- any other parameter must have a default value: it becomes a component property, which can be
  overridden in application.yml;
- for a YCappuccinoComponentBind, the type of the ``bind`` parameter declares an aggregate
  dependency whose services are given to ``bind`` / ``un_bind``.

The component is published under its class name and the names of the YCappuccino interfaces
it implements.
"""

import dataclasses
import importlib
import inspect
import logging
import types
import typing
from types import ModuleType
from typing import Any, Optional
from urllib.parse import parse_qsl, urlsplit

import pelix.http as http
import pelix.remote
from pelix.ipopo.constants import IPOPO_FACTORY_CONTEXT
from pelix.ipopo.decorators import (
    BindField,
    ComponentFactory,
    Instantiate,
    Invalidate,
    Property,
    Provides,
    Requires,
    UnbindField,
    Validate,
)

from ycappuccino.api.core_base import (
    YCappuccinoComponent,
    YCappuccinoComponentBind,
    _YCappuccinoType,
)
from ycappuccino.api.http import HttpRequest, HttpResponse, IHttpServlet
from ycappuccino.api.proxy import Proxy, YCappuccinoRemote

# classes whose subclasses are service specifications
_INTERFACE_ROOTS = (YCappuccinoComponent, YCappuccinoRemote)
# base classes that are never published
_FRAMEWORK_CLASSES = (YCappuccinoComponent, YCappuccinoComponentBind)


@dataclasses.dataclass(frozen=True)
class Requirement:
    field: str
    specification: str
    optional: bool = False
    spec_filter: Optional[str] = None
    aggregate: bool = False


@dataclasses.dataclass(frozen=True)
class Binding:
    field: str
    specification: str


@dataclasses.dataclass
class ComponentDescription:
    component: type
    provides: list = dataclasses.field(default_factory=list)
    # provides_qualified[i] is the fully-qualified "module.QualName" path of the specification
    # whose short name is provides[i] - same index, same specification. Resolve it back to the
    # real class with resolve_class(). The one exception is the Pelix HTTP servlet marker
    # ("pelix.http.servlet", added when the component implements IHttpServlet): it is not a
    # Python class, so it appears identically in both lists at its index and is not resolvable.
    provides_qualified: list = dataclasses.field(default_factory=list)
    requires: list = dataclasses.field(default_factory=list)
    properties: dict = dataclasses.field(default_factory=dict)
    bindings: list = dataclasses.field(default_factory=list)

    @property
    def name(self) -> str:
        return f"{self.component.__module__}.{self.component.__qualname__}"

    @property
    def factory_name(self) -> str:
        return self.name + "-Factory"


def resolve_class(dotted_path: str) -> type:
    """the class designated by a "module.ClassName" dotted path"""
    module_name, separator, class_name = dotted_path.rpartition(".")
    if not separator:
        raise ValueError(f"{dotted_path!r} is not a dotted 'module.ClassName' path")
    module = importlib.import_module(module_name)
    try:
        return getattr(module, class_name)
    except AttributeError:
        raise ImportError(f"module {module_name!r} has no class {class_name!r}") from None


def is_ipopo_component(klass: Any) -> bool:
    """true for classes already manipulated by the iPOPO decorators (legacy bundles)"""
    context = getattr(klass, IPOPO_FACTORY_CONTEXT, None)
    return context is not None and context.completed


def is_component(klass: Any) -> bool:
    """true for classes the framework must turn into iPOPO components"""
    return (
        inspect.isclass(klass)
        and issubclass(klass, YCappuccinoComponent)
        and not issubclass(klass, _YCappuccinoType)
        and not inspect.isabstract(klass)
        and not is_ipopo_component(klass)
    )


def describe_component(klass: type) -> ComponentDescription:
    """read the wiring of a component from its constructor and bind method"""
    provides, provides_qualified = _provided_specifications(klass)
    description = ComponentDescription(klass, provides=provides, provides_qualified=provides_qualified)

    for parameter, annotation in _constructor_parameters(klass):
        dependency = _dependency(annotation)
        if dependency is not None:
            specification, spec_filter, optional, aggregate = dependency
            description.requires.append(
                Requirement(
                    parameter.name,
                    specification,
                    optional or parameter.default is None,
                    spec_filter,
                    aggregate,
                )
            )
        elif parameter.default is not inspect.Parameter.empty:
            description.properties[parameter.name] = parameter.default
        else:
            raise TypeError(
                f"{description.name}: parameter '{parameter.name}' can't be injected, "
                "type it with a component interface or give it a default value"
            )

    if issubclass(klass, YCappuccinoComponentBind):
        description.bindings = _bindings(klass)

    if issubclass(klass, IHttpServlet):
        description.provides.append(http.HTTP_SERVLET)
        description.provides_qualified.append(http.HTTP_SERVLET)
        if "path" not in description.properties:
            raise TypeError(f"{description.name} implements IHttpServlet but declares no 'path' property")

    return description


def create_factory_module(
    description: ComponentDescription,
    runner,
    instance_properties: Optional[dict] = None,
    name: Optional[str] = None,
) -> ModuleType:
    """
    build a module holding the iPOPO factory of the component, to install as a Pelix bundle.
    The factory is instantiated once and publishes a Proxy to the component object.

    `name` overrides the module/instance/factory identifier (default: description.name). Pass a
    unique name to turn the same class into several independent runtime instances, as
    Framework.instantiate_component does.
    """
    component = description.component
    instance_name = name or description.name
    module = ModuleType(instance_name + "_ipopo")
    list_fields = {
        _require_field(requirement.field) for requirement in description.requires if requirement.aggregate
    }
    bind_fields = {binding.field for binding in description.bindings}

    def validate(self, context):
        self._ycappuccino_lists = {field: [] for field in list_fields}
        self._ycappuccino_bound = {}
        arguments = {}
        for requirement in description.requires:
            field = _require_field(requirement.field)
            if requirement.aggregate:
                for service in getattr(self, field) or ():
                    _add_service(self, field, service)
                arguments[requirement.field] = self._ycappuccino_lists[field]
            else:
                arguments[requirement.field] = _unwrap(getattr(self, field))
        for name in description.properties:
            arguments[name] = getattr(self, _property_field(name))

        self._obj = component(**arguments)
        try:
            for binding in description.bindings:
                for service in getattr(self, binding.field) or ():
                    runner.run(self._obj.bind(_unwrap(service)))
            runner.run(self._obj.start())
        except BaseException:
            self._obj = None
            raise

    def invalidate(self, context):
        component_object, self._obj = self._obj, None
        self._ycappuccino_lists = None
        self._ycappuccino_bound = None
        if component_object is not None:
            runner.run(component_object.stop())

    namespace = {
        "__module__": module.__name__,
        "_ycappuccino_lists": None,
        "_ycappuccino_bound": None,
        "_ycappuccino_validate": Validate(validate),
        "_ycappuccino_invalidate": Invalidate(invalidate),
    }

    if list_fields or bind_fields:

        def bind(self, field, service, service_reference):
            if field in list_fields:
                # services bound before validation are added to the list by validate
                if self._ycappuccino_lists is not None:
                    _add_service(self, field, service)
            elif self._obj is not None:
                runner.run(self._obj.bind(_unwrap(service)))

        def unbind(self, field, service, service_reference):
            if field in list_fields:
                if self._ycappuccino_lists is not None:
                    _remove_service(self, field, service)
            elif self._obj is not None:
                runner.run(self._obj.un_bind(_unwrap(service)))

        for field in sorted(list_fields | bind_fields):
            bind = BindField(field)(bind)
            unbind = UnbindField(field)(unbind)
        namespace["_ycappuccino_bind"] = bind
        namespace["_ycappuccino_unbind"] = unbind

    if issubclass(component, IHttpServlet):
        def _http_request(pelix_request, method: str) -> "HttpRequest":
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
                    logging.getLogger(component.__module__).exception("servlet %s failed on %s", component.__qualname__, request.path)
                    result = HttpResponse(status=500, body=b"", content_type="text/plain")
                _send(pelix_response, result)
            return handler

        for verb in ("GET", "POST", "PUT", "DELETE"):
            namespace[f"do_{verb}"] = _do(verb)

        # Override __getattribute__ to allow servlet methods to be accessed
        # even though they're on the proxy class, not the wrapped object
        _servlet_methods = frozenset(("do_GET", "do_POST", "do_PUT", "do_DELETE"))
        _original_getattribute = namespace.get("__getattribute__", Proxy.__getattribute__)

        def __getattribute__(self, name: str):
            if name in _servlet_methods:
                return object.__getattribute__(self, name)
            return _original_getattribute(self, name)

        namespace["__getattribute__"] = __getattribute__

    factory_class = type(component.__name__ + "IpopoProxy", (Proxy,), namespace)

    for requirement in description.requires:
        factory_class = Requires(
            _require_field(requirement.field),
            requirement.specification,
            aggregate=requirement.aggregate,
            optional=requirement.optional,
            spec_filter=requirement.spec_filter,
        )(factory_class)
    for binding in description.bindings:
        factory_class = Requires(
            binding.field, binding.specification, aggregate=True, optional=True
        )(factory_class)
    for name, value in description.properties.items():
        factory_class = Property(_property_field(name), name, value)(factory_class)

    if issubclass(component, IHttpServlet):
        path_value = (instance_properties or {}).get("path", description.properties.get("path"))
        factory_class = Property("_ycappuccino_http_path", http.HTTP_SERVLET_PATH, path_value)(factory_class)
        factory_class = Property(
            "_ycappuccino_http_reject", pelix.remote.PROP_EXPORT_REJECT, http.HTTP_SERVLET
        )(factory_class)

    factory_class = Provides(description.provides)(factory_class)
    factory_class = Instantiate(instance_name, dict(instance_properties or {}))(factory_class)
    factory_class = ComponentFactory(instance_name + "-Factory")(factory_class)

    setattr(module, factory_class.__name__, factory_class)
    return module


def _require_field(name: str) -> str:
    return "_ycappuccino_require_" + name


def _property_field(name: str) -> str:
    return "_ycappuccino_property_" + name


def _unwrap(service: Any) -> Any:
    """the component object behind a generated proxy, other services as they are"""
    if isinstance(service, Proxy):
        return object.__getattribute__(service, "_obj")
    return service


def _add_service(proxy, field: str, service: Any) -> None:
    """add the component object of a bound service to the live list of the field, once"""
    key = (field, id(service))
    if key not in proxy._ycappuccino_bound:
        component_object = _unwrap(service)
        proxy._ycappuccino_bound[key] = component_object
        proxy._ycappuccino_lists[field].append(component_object)


def _remove_service(proxy, field: str, service: Any) -> None:
    key = (field, id(service))
    if key not in proxy._ycappuccino_bound:
        return
    component_object = proxy._ycappuccino_bound.pop(key)
    services = proxy._ycappuccino_lists[field]
    for index, element in enumerate(services):
        if element is component_object:
            del services[index]
            return


def _dependency(annotation: Any) -> Optional[tuple]:
    """(specification, spec_filter, optional, aggregate) when the annotation designates components"""
    if typing.get_origin(annotation) is list:
        arguments = typing.get_args(annotation)
        element = _dependency(arguments[0]) if len(arguments) == 1 else None
        if element is None or element[3]:
            return None
        return element[0], element[1], True, True

    optional = False
    if typing.get_origin(annotation) in (typing.Union, types.UnionType):
        arguments = [argument for argument in typing.get_args(annotation) if argument is not type(None)]
        if len(arguments) != 1:
            return None
        annotation, optional = arguments[0], True

    if not inspect.isclass(annotation):
        return None
    if issubclass(annotation, _YCappuccinoType):
        return annotation.type.__name__, annotation.spec_filter, optional, False
    if issubclass(annotation, _INTERFACE_ROOTS):
        return annotation.__name__, None, optional, False
    return None


def _parameters(function) -> list:
    """(parameter, resolved annotation) of a method, without self, *args and **kwargs"""
    try:
        hints = typing.get_type_hints(function)
    except Exception:
        hints = {}
    parameters = list(inspect.signature(function).parameters.values())[1:]
    return [
        (parameter, hints.get(parameter.name, parameter.annotation))
        for parameter in parameters
        if parameter.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    ]


def _constructor_parameters(klass: type) -> list:
    if klass.__init__ is object.__init__:
        return []
    return _parameters(klass.__init__)


def _bindings(klass: type) -> list:
    bindings = []
    for parameter, annotation in _parameters(klass.bind):
        dependency = _dependency(annotation)
        if dependency is not None:
            bindings.append(Binding("_ycappuccino_bind_" + parameter.name, dependency[0]))
    return bindings


def _provided_specifications(klass: type) -> tuple:
    """(short names, fully-qualified dotted paths), index-aligned - see ComponentDescription"""
    specifications = []
    qualified = []
    for base in klass.__mro__:
        if base in _FRAMEWORK_CLASSES:
            continue
        if base is klass or issubclass(base, _INTERFACE_ROOTS):
            if base.__name__ not in specifications:
                specifications.append(base.__name__)
                qualified.append(f"{base.__module__}.{base.__qualname__}")
    return specifications, qualified
