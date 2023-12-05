from __future__ import annotations

import inspect
import logging
from abc import ABCMeta, abstractmethod
from collections import defaultdict
from copy import deepcopy
from functools import lru_cache
from typing import _GenericAlias  # type: ignore
from typing import (
    Any,
    Callable,
    ForwardRef,
    Generic,
    TypeVar,
    cast,
    get_type_hints,
    overload,
)

from typing_extensions import dataclass_transform

try:
    from types import GenericAlias

    _generic_alias_types: tuple = (_GenericAlias, GenericAlias)
except ImportError:
    _generic_alias_types = (_GenericAlias,)

from .config import Config, ConfigProperty, DefaultConfig
from .context import Context
from .exceptions import InvalidAttrDefinition
from .runs.base import RunTracker
from .settings import settings
from .utils.modules import (
    ObjectInitDeclaration,
    deserialize,
    import_dotted_string,
    serialize,
)
from .utils.pretties import unflatten_dict
from .utils.typings import (
    input_signature,
    is_compatible_with,
    is_union_type,
    output_signature,
)
from .visualization import trace_pipelne_run

logger = logging.getLogger(__name__)


def is_node_type(annotation) -> bool:
    """Return True if the annotation contains Function"""
    if is_union_type(annotation):
        return any(is_node_type(a) for a in annotation.__args__)
    if isinstance(annotation, ForwardRef):
        annotation = annotation._evaluate(globals(), locals(), frozenset())
        return is_node_type(annotation)
    if isinstance(annotation, _generic_alias_types):
        return issubclass(annotation.__origin__, NodeAttr)
    if isinstance(annotation, type):
        return issubclass(annotation, Function) or issubclass(annotation, NodeAttr)
    return False


class unset_:
    def __bool__(self):
        return False

    def __persist_flow__(self):
        type_ = f"{self.__module__}.{self.__class__.__qualname__}"
        return {"__type__": type_}


unset = unset_()

_Attr = TypeVar("_Attr")
_PAttr = TypeVar("_PAttr")
_NAttr = TypeVar("_NAttr", bound="Function")


class Attr(Generic[_Attr]):
    """Decriptor to store function attributes

    Args:
        default: default value of the parameter
        default_callback: callback function to generate default attribute value. This
            callback takes in the Function object and output the default value.
        auto_callback: callback function to generate attribute value. This
            callback takes in the Function object and output the default value.
        cache: if True, the value of the parameter will not be cached and will be
            recalculated everytime it is accessed (requires `auto_callback`)
        depends_on: if set, the value of the parameter will be calculated from the
            values of the depends_on parameters (requires `cache=True`)
        help: help message for the attribute
    """

    def __init__(
        self,
        default: _Attr | ObjectInitDeclaration[_Attr] | unset_ | type = unset,
        *,
        default_callback: Callable[[Any], _Attr] | unset_ = unset,
        auto_callback: Callable[[Any], _Attr] | unset_ = unset,
        cache: bool = False,
        depends_on: str | list[str] | None = None,
        help: str = "",
        **extras,
    ):
        self._default: _Attr = cast(_Attr, default)
        self._default_callback = default_callback
        self._auto_callback = auto_callback
        self._help = help
        self._extras = extras

        self._cache = cache

        if isinstance(depends_on, str):
            depends_on = [depends_on]
        self._depends_on: list[str] | None = depends_on
        self._to_check = depends_on or []

        self._attrx = self.__class__.__name__

    def __str__(self):
        text = ", ".join(
            [
                f"{key}={value}"
                for key, value in self.to_dict().items()
                if not key.startswith("_")
            ]
        )
        return f"{self.__class__.__name__}({text})"

    def __repr__(self):
        return str(self)

    @overload
    def __get__(self, obj: None, _: type[Function] | None) -> Attr:
        ...

    @overload
    def __get__(self, obj: Function, _: type[Function] | None) -> _Attr:
        ...

    def __get__(
        self, obj: Function | None, _: type[Function] | None = None
    ) -> _Attr | Attr:
        """Get the value of the parameter"""
        if obj is None:
            return self

        if not isinstance(obj, Function):
            raise ValueError(
                f"`{self.__class__.__name__}` can only be used with Function: "
                f"{self._qual_name}"
            )

        if not isinstance(self._auto_callback, unset_):
            value = self._auto_calculate_param(obj)
        elif self._name in obj._attrx[self._attrx]:
            value = obj._attrx[self._attrx][self._name]
        elif self._default != unset:
            if isinstance(self._default, ObjectInitDeclaration):
                value = self._default()
            else:
                value = deepcopy(self._default)
            value = cast(_Attr, value)
        elif not isinstance(self._default_callback, unset_):
            value = self._default_callback(obj)
        else:
            raise AttributeError(
                f"{self._attrx} {self._qual_name} is not set and has no default value"
            )

        obj._attrx[self._attrx][self._name] = value
        return value

    def __set__(self, obj: Function, value: Any):
        if self._auto_callback != unset:
            raise ValueError(
                f"Cannot set value for auto-calculated {self._attrx}: {self._qual_name}"
            )
        obj._attrx[self._attrx][self._name] = value

    def __delete__(self, obj: Function):
        if self._auto_callback != unset:
            raise ValueError(
                f"Cannot delete value for auto-calculated parameter: {self._qual_name}"
            )

        if self._name in obj._attrx[self._attrx]:
            del obj._attrx[self._attrx][self._name]

    def __set_name__(self, owner: type, name: str):
        self._name = name
        self._owner = owner
        self._qual_name = (
            f"{self._owner.__module__}.{self._owner.__name__}.{self._name}"
        )

        # validate after receiving the name and type for actionable error message
        self._validate_args()

    def __persist_flow__(self):
        """Return the state in a way that can be initiated"""
        export = {}
        for key, value in self.to_dict().items():
            try:
                serialized = serialize(value)
            except Exception as e:
                type_ = f"{self._owner.__module__}.{self._owner.__qualname__}"
                logger.debug(f"{type_}.{self._name}.{key}: {e}... skip")
                serialized = serialize(unset)
            export[key] = serialized

        return export

    def _auto_calculate_param(self, obj: Function) -> _Attr:
        """Calculate the value of the auto-parameter

        Args:
            obj: the Function object

        Returns:
            the value of the parameter
        """
        if isinstance(self._auto_callback, unset_):
            raise ValueError(
                f"Cannot calculate auto-parameter without auto_callback: "
                f"{self._qual_name}"
            )

        if not self._cache:
            return self._auto_callback(obj)

        if not self._to_check:
            for attr in dir(obj.__class__):
                if attr == self._name:
                    continue

                # TODO: leaky abstraction of child class here. Attr
                # shouldn't have knowledge about ParamAttr or NodeAttr
                if isinstance(getattr(obj.__class__, attr), ParamAttr):
                    self._to_check.append(attr)
                if isinstance(getattr(obj.__class__, attr), NodeAttr):
                    self._to_check.append(attr)

        ids = {}
        must_recalculate = False
        for target in self._to_check:
            old_id = obj.__ff_depends__[self._name].get(target, -1)
            new_id = id(getattr(obj, target))
            ids[target] = new_id

            if old_id != new_id:
                must_recalculate = True
                break

        if must_recalculate:
            value = self._auto_callback(obj)
            # calculate new hash
            for target in self._to_check:
                id_ = ids[target] if target in ids else id(getattr(obj, target))
                obj.__ff_depends__[self._name][target] = id_
        else:
            value = obj._attrx[self._attrx][self._name]

        return value

    def _validate_args(self):
        """Validate the __init__ args"""
        if (
            sum(
                [
                    self._default != unset,
                    self._default_callback != unset,
                    self._auto_callback != unset,
                ]
            )
            > 1
        ):
            raise InvalidAttrDefinition(
                "Only one of `default`, `default_callback`, `auto_callback` can be set:"
                f" {self._qual_name}"
            )

        if self._cache and self._auto_callback == unset:
            raise InvalidAttrDefinition(
                f"`cache=True` only applies for `auto_callback`: {self._qual_name}"
            )

        if self._depends_on and not self._cache:
            raise InvalidAttrDefinition(
                f"`depends_on` only applies for `cache=True`: {self._qual_name}"
            )

    @classmethod
    def default(
        cls,
        *,
        refresh_on_set: bool = False,
        strict_type: bool = False,
        **kwargs,
    ):
        """Method decorator to create default callback"""
        # TODO: can consider remove .default, since this is not commonly used and can
        # cause visual confusion with .auto, which is much more frequently used.
        if kwargs.get("help"):
            raise ValueError(
                "Please set `help` as function docstring when use `default` decorator"
            )

        def inner(func):
            help_: str = inspect.getdoc(func) or ""
            return cls(
                default_callback=func,
                help=help_,
                refresh_on_set=refresh_on_set,
                strict_type=strict_type,
                **kwargs,
            )

        return inner

    @classmethod
    def auto(
        cls,
        *,
        cache: bool = True,
        depends_on: str | list[str] | None = None,
        **kwargs,
    ):
        """Method decorator to create auto callback"""
        if kwargs.get("help"):
            raise ValueError(
                "Please set `help` as function docstring when use `auto` decorator"
            )

        def inner(func):
            help_: str = inspect.getdoc(func) or ""
            return cls(
                auto_callback=func,
                help=help_,
                depends_on=depends_on,
                cache=cache,
                **kwargs,
            )

        return inner

    def to_dict(self) -> dict:
        """Return the internal state of the Param as a dict"""
        return {
            "__type__": f"{self.__module__}.{self.__class__.__qualname__}",
            "default": self._default,
            "default_callback": self._default_callback,
            "auto_callback": self._auto_callback,
            "help": self._help,
            "depends_on": self._depends_on,
            "cache": self._cache,
            **self._extras,
        }


class ParamAttr(Attr[_PAttr]):
    """Control the behavior of a parameter in a Function

    Args:
        default: default value of the parameter
        default_callback: callback function to generate default attribute value. This
            callback takes in the Function object and output the default value.
        auto_callback: callback function to generate attribute value. This
            callback takes in the Function object and output the default value.
        cache: if True, the value of the parameter will not be cached and will be
            recalculated everytime it is accessed (requires `auto_callback`)
        depends_on: if set, the value of the parameter will be calculated from the
            values of the depends_on parameters (requires `cache=True`)
        help: help message for the attribute
        refresh_on_set: if True, the original object will be refreshed when it is set
        strict_type: if True, the type of the value will be checked when it is set
    """

    def __init__(
        self,
        default: _PAttr | ObjectInitDeclaration[_PAttr] | unset_ = unset,
        *,
        default_callback: Callable[[Any], _PAttr] | unset_ = unset,
        auto_callback: Callable[[Any], _PAttr] | unset_ = unset,
        cache: bool = False,
        depends_on: str | list[str] | None = None,
        help: str = "",
        refresh_on_set: bool = False,
        strict_type: bool = False,
        **extras,
    ):
        super().__init__(
            default=default,
            default_callback=default_callback,
            auto_callback=auto_callback,
            cache=cache,
            depends_on=depends_on,
            help=help,
            **extras,
        )

        # param-specific attributes
        self._refresh_on_set = refresh_on_set
        self._strict_type = strict_type
        self._type = None
        self._attrx = "ParamAttr"

    def __set__(self, obj: Function, value: Any):
        if self._strict_type:
            if not isinstance(value, obj.__dict__["__annotations__"][self._name]):
                # TODO: more sophisicated type checking (e.g. handle Union, Optional...)
                raise ValueError(
                    f"Value {value} is not of type {type(self._default)} "
                    f"for parameter {self._name}"
                )

        super().__set__(obj, value)
        if self._refresh_on_set:
            obj._initialize()

    def __delete__(self, obj: Function):
        super().__delete__(obj)
        if self._refresh_on_set:
            obj._initialize()

    @overload
    def __get__(self, obj: None, _: type[Function] | None) -> ParamAttr:
        ...

    @overload
    def __get__(self, obj: Function, _: type[Function] | None) -> _PAttr:
        ...

    def __get__(
        self, obj: Function | None, _: type[Function] | None = None
    ) -> _PAttr | ParamAttr:
        if obj is None:
            return self

        try:
            return super().__get__(obj, _)
        except AttributeError as e:
            if obj.config.params_subscribe and obj._ff_prefix:
                context = f"{obj.flow_qualidx()}|published_params"
                if not obj.context.has_context(context):
                    raise e
                value = obj.context.get(
                    name=self._name,
                    default=unset,
                    context=context,
                )
                if value != unset:
                    obj._attrx[self._attrx][self._name] = value
                    return value
            raise e

    @classmethod
    def auto(
        cls,
        *,
        refresh_on_set: bool = False,
        strict_type: bool = False,
        cache: bool = True,
        depends_on: str | list[str] | None = None,
        **kwargs,
    ) -> Callable[[Callable[[Any], _PAttr]], ParamAttr[_PAttr]]:
        """Automatically set this method as param's `auto_callback`

        If cached is not enabled, the value will be recalculated everytime. Otherwise,
        the value will be recalculated in case all other nodes and parameters that
        this node depends on have changed.

        As comparing all values for cache can be expensive, you can list the name
        of relevant nodes and params in `depends_on` to limit the comparison to
        only these nodes and params.

        Args:
            refresh_on_set: whether to refresh the graph when the parameter is set
            strict_type: whether to check the type of the value when the param is set
            cache: whether to cache the value of the parameter
            depends_on: the name of nodes and params that this node depends on
        """
        return super().auto(
            cache=cache,
            depends_on=depends_on,
            refresh_on_set=refresh_on_set,
            strict_type=strict_type,
            **kwargs,
        )

    @classmethod
    def default(
        cls,
        *,
        refresh_on_set: bool = False,
        strict_type: bool = False,
        **kwargs,
    ) -> Callable[[Callable[[Any], _PAttr]], ParamAttr[_PAttr]]:
        """Automatically set this method as param's `default_callback`

        When this param is accessed while unset, this method will return the default
        value

        Args:
            refresh_on_set: whether to refresh the graph when the parameter is set
            strict_type: whether to check the type of the value when the param is set
        """
        return super().default(
            refresh_on_set=refresh_on_set,
            strict_type=strict_type,
            **kwargs,
        )

    def to_dict(self) -> dict:
        """Return the internal state of the Param as a dict"""
        d = super().to_dict()
        d["refresh_on_set"] = self._refresh_on_set
        d["strict_type"] = self._strict_type
        return d


class NodeAttr(Attr[_NAttr]):
    """Control the behavior of a node in a Function

    Args:
        default: default value of the parameter
        default_callback: callback function to generate default attribute value. This
            callback takes in the Function object and output the default value.
        auto_callback: callback function to generate attribute value. This
            callback takes in the Function object and output the default value.
        cache: if True, the value of the parameter will not be cached and will be
            recalculated everytime it is accessed (requires `auto_callback`)
        depends_on: if set, the value of the parameter will be calculated from the
            values of the depends_on parameters (requires `cache=True`)
        help: help message for the attribute
        input: the input signature of the node
        output: the output signature of the node
    """

    def __init__(
        self,
        default: type[_NAttr] | ObjectInitDeclaration[_NAttr] | unset_ = unset,
        *,
        default_callback: Callable[[Any], _NAttr] | unset_ = unset,
        auto_callback: Callable[[Any], _NAttr] | unset_ = unset,
        cache: bool = False,
        depends_on: str | list[str] | None = None,
        help: str = "",
        input: unset_ | dict[str, Any] = unset,
        output: Any = unset,
        **extras,
    ):
        if inspect.isclass(default) and issubclass(default, Function):
            default = cast(ObjectInitDeclaration, ObjectInitDeclaration(default))
        super().__init__(
            default=default,
            default_callback=default_callback,
            auto_callback=auto_callback,
            cache=cache,
            depends_on=depends_on,
            help=help,
            **extras,
        )

        self._input: unset_ | dict[str, Any] = input
        self._output: Any = output

        has_run_method = callable(getattr(default, "run", None))
        if self._input == unset and has_run_method:
            self._input = input_signature(default.run)  # type: ignore
        if self._output == unset and has_run_method:
            self._output = output_signature(default.run)  # type: ignore

        self._attrx = "NodeAttr"

    @overload
    def __get__(self, obj: None, _: type[Function] | None) -> NodeAttr:
        ...

    @overload
    def __get__(self, obj: Function, _: type[Function] | None) -> _NAttr:
        ...

    def __get__(self, obj: Function | None, _: type[Function] | None = None):
        value = super().__get__(obj, _)
        if obj:
            value = cast(_NAttr, value)
            obj._prepare_child(value, self._name)
            if not isinstance(value, Function):
                raise ValueError(f"Node {obj.__class__}.{self._name} is not a Function")
            return value
        return value

    @classmethod
    def auto(
        cls,
        *,
        input: unset_ | dict[str, Any] = unset,
        output: Any = unset,
        cache: bool = True,
        depends_on: str | list[str] | None = None,
        **kwargs,
    ) -> Callable[[Callable[[Any], _NAttr]], NodeAttr[_NAttr]]:
        """Automatically set this method as param's `auto_callback`

        If cached is not enabled, the value will be recalculated everytime. Otherwise,
        the value will be recalculated in case all other nodes and parameters that
        this node depends on have changed.

        As comparing all values for cache can be expensive, you can list the name
        of relevant nodes and params in `depends_on` to limit the comparison to
        only these nodes and params.

        Args:
            refresh_on_set: whether to refresh the graph when the parameter is set
            strict_type: whether to check the type of the value when the param is set
            cache: whether to cache the value of the parameter
            depends_on: the name of nodes and params that this node depends on
        """
        return super().auto(
            cache=cache,
            depends_on=depends_on,
            input=input,
            output=output,
            **kwargs,
        )

    @classmethod
    def default(
        cls,
        *,
        input: unset_ | dict[str, Any] = unset,
        output: Any = unset,
        **kwargs,
    ) -> Callable[[Callable[[Any], _NAttr]], NodeAttr[_NAttr]]:
        """Automatically set this method as param's `default_callback`

        When this param is accessed while unset, this method will return the default
        value

        Args:
            refresh_on_set: whether to refresh the graph when the parameter is set
            strict_type: whether to check the type of the value when the param is set
        """
        return super().default(
            input=input,
            output=output,
            **kwargs,
        )

    def to_dict(self) -> dict:
        """Return the internal state of a node as dict"""
        d = super().to_dict()
        d["input"] = self._input
        d["output"] = self._output
        return d


_node_cls: type[NodeAttr] = (
    deserialize(settings.NODE_CLASS, safe=False)
    if getattr(settings, "NODE_CLASS", "")
    else NodeAttr
)


_param_cls: type[ParamAttr] = (
    deserialize(settings.PARAM_CLASS, safe=False)
    if getattr(settings, "PARAM_CLASS", "")
    else ParamAttr
)


class _ParamWrapper:
    """Wrapper class to create a Param object

    This way, users can declare Param with both Param(...) and Param.auto(...)"""

    def __call__(
        self,
        default: _PAttr | ObjectInitDeclaration[_PAttr] | unset_ = unset,
        *,
        default_callback: Callable[[Any], _PAttr] | unset_ = unset,
        auto_callback: Callable[[Any], _PAttr] | unset_ = unset,
        cache: bool = False,
        depends_on: str | list[str] | None = None,
        help: str = "",
        refresh_on_set: bool = False,
        strict_type: bool = False,
        **extras,
    ) -> Any:
        return _param_cls(
            default=default,
            default_callback=default_callback,
            auto_callback=auto_callback,
            cache=cache,
            depends_on=depends_on,
            help=help,
            refresh_on_set=refresh_on_set,
            strict_type=strict_type,
            **extras,
        )

    def auto(
        self,
        *,
        refresh_on_set: bool = False,
        strict_type: bool = False,
        cache: bool = True,
        depends_on: str | list[str] | None = None,
        **kwargs,
    ) -> Callable[[Callable[[Any], _PAttr]], ParamAttr[_PAttr]]:
        """Automatically set this method as param's `auto_callback`

        If cached is not enabled, the value will be recalculated everytime. Otherwise,
        the value will be recalculated in case all other nodes and parameters that
        this node depends on have changed.

        As comparing all values for cache can be expensive, you can list the name
        of relevant nodes and params in `depends_on` to limit the comparison to
        only these nodes and params.

        Args:
            refresh_on_set: whether to refresh the graph when the parameter is set
            strict_type: whether to check the type of the value when the param is set
            cache: whether to cache the value of the parameter
            depends_on: the name of nodes and params that this node depends on
        """
        return _param_cls.auto(
            cache=cache,
            depends_on=depends_on,
            refresh_on_set=refresh_on_set,
            strict_type=strict_type,
            **kwargs,
        )


class _NodeWrapper:
    """Wrapper class to create a Node object

    This way, users can declare Node with both Node(...) and Node.auto(...)"""

    def __call__(
        self,
        default: type[_NAttr] | ObjectInitDeclaration[_NAttr] | unset_ = unset,
        *,
        default_callback: Callable[[Any], _NAttr] | unset_ = unset,
        auto_callback: Callable[[Any], _NAttr] | unset_ = unset,
        cache: bool = False,
        depends_on: str | list[str] | None = None,
        help: str = "",
        input: unset_ | dict[str, Any] = unset,
        output: Any = unset,
        **extras,
    ) -> Any:
        return _node_cls(
            default=default,
            default_callback=default_callback,
            auto_callback=auto_callback,
            cache=cache,
            depends_on=depends_on,
            help=help,
            input=input,
            output=output,
            **extras,
        )

    def auto(
        self,
        *,
        input: unset_ | dict[str, Any] = unset,
        output: Any = unset,
        cache: bool = True,
        depends_on: str | list[str] | None = None,
        **kwargs,
    ) -> Callable[[Callable[[Any], _NAttr]], NodeAttr[_NAttr]]:
        """Automatically set this method as param's `auto_callback`

        If cached is not enabled, the value will be recalculated everytime. Otherwise,
        the value will be recalculated in case all other nodes and parameters that
        this node depends on have changed.

        As comparing all values for cache can be expensive, you can list the name
        of relevant nodes and params in `depends_on` to limit the comparison to
        only these nodes and params.

        Args:
            refresh_on_set: whether to refresh the graph when the parameter is set
            strict_type: whether to check the type of the value when the param is set
            cache: whether to cache the value of the parameter
            depends_on: the name of nodes and params that this node depends on
        """
        return _node_cls.auto(
            cache=cache,
            depends_on=depends_on,
            input=input,
            output=output,
            **kwargs,
        )


Node = _NodeWrapper()
Param = _ParamWrapper()


class MetaFunction(ABCMeta):
    def __new__(cls, clsname, bases, attrs):
        # Will deprecate in Python 3.13. Now we needs to create the obj to reliably
        # obtain type annotations.
        _obj: type[Function] = super().__new__(
            cls, clsname, bases, attrs  # type: ignore
        )

        # Make sure all nodes and params have the Node and Param descriptor
        for name, value in get_type_hints(_obj).items():
            if name not in attrs.get("__annotations__", {}):
                continue
            if name.startswith("_"):
                continue
            if name in attrs and isinstance(attrs[name], (NodeAttr, ParamAttr)):
                continue
            desc: NodeAttr | ParamAttr
            if is_node_type(value):
                desc = _node_cls(default=attrs[name]) if name in attrs else _node_cls()
            else:
                desc = (
                    _param_cls(default=attrs[name]) if name in attrs else _param_cls()
                )
            attrs[name] = desc

        try:
            obj: type[Function] = super().__new__(
                cls, clsname, bases, attrs  # type: ignore
            )
        except Exception as e:
            cause = getattr(e, "__cause__", None)
            if isinstance(cause, InvalidAttrDefinition):
                raise cause from None
            raise e from None

        # Raise invalid nodes and params
        for name, value in attrs.items():
            if not isinstance(value, (NodeAttr, ParamAttr)):
                continue
            if name.startswith("_"):
                raise ValueError(f"Node and param name cannot start with _: {name}")

            if name in obj._protected_keywords():
                raise ValueError(
                    f'"{name}" is a protected keyword, defined by '
                    f'"{obj._protected_keywords()[name]}"'
                )
        return obj


@dataclass_transform(
    eq_default=False,
    kw_only_default=True,
    field_specifiers=(Param, Node),  # type: ignore
)
class Function(metaclass=MetaFunction):
    """Base class that handle basic logic of a composable component

    Everything is a composable component. Subclass `Function` to define and run your
    own flow or component.

    This class:
        - Manages input parameters
        - Set up _ff_config and _ff_context
        - Defines base

    Initialization order:
        - initiate the parameters (by default inside __init__)
        - initiate the config and context
        - initiate the nodes

    Private attributes:
        _params: parameters that are passed by the user (e.g. during __init__ or by
            setattr)

    Parameters and nodes have to be declared so that the information about the
    Function is explicit.
    """

    Config = DefaultConfig
    config = ConfigProperty()

    _keywords = [
        "Config",
        "abs_pathx",
        "apply",
        "config",
        "context",
        "describe",
        "dump",
        "flow_qualidx",
        "get_from_path",
        "getx",
        "idx",
        "is_compatible",
        "last_run",
        "log_progress",
        "missing",
        "namex",
        "nodes",
        "params",
        "parent_qualidx",
        "qualidx",
        "run",
        "set",
        "set_run",
        "specs",
        "visualize",
        "withx",
    ]

    def __init__(self, _params: dict | None = None, /, **params):
        self.last_run: RunTracker
        self._track_child: bool = True
        self._attrx: dict[str, dict[str, Any]] = {
            "NodeAttr": {},
            "ParamAttr": {},
            "AllowExtraParam": {},
        }
        self.__ff_depends__: dict[str, dict[str, int]] = defaultdict(dict)
        self.__ff_run_kwargs__: dict[str, Any] = {}
        self._ff_params: list[str] = []
        self._ff_nodes: list[str] = []
        self._ff_config: Config = Config(cls=self.__class__)
        self._ff_context: Context | None = None

        # Initialize temporary execution variables
        self._variablex()

        # collect
        self._ff_params, self._ff_nodes = self._collect_registered_params_and_nodes()

        self._ff_init_called = False
        if _params:
            self.set(_params)
        if params:
            self.set(params)
        self._ff_init_called = True

        # collect middleware
        middleware_section: str = self.config.middleware_section
        middleware_setting = settings.MIDDLEWARE
        if middleware_section not in middleware_setting:
            raise ValueError(
                f'Middleware section "{middleware_section}" not found in settings'
            )
        middleware_switches = self.config.middleware_switches

        self._middleware = None
        if middlware_cfg := middleware_setting[middleware_section]:
            next_call = self._runx
            for cls_name in reversed(middlware_cfg):
                if not middleware_switches.get(cls_name, True):
                    continue
                cls = import_dotted_string(cls_name, safe=False)
                next_call = cls(obj=self, next_call=next_call)
            self._middleware = next_call

        if not hasattr(self, "_ff_initializing"):
            # TODO: this work better if we formulate config and context as independent
            self._initialize()

    def _variablex(self):
        """Set temporary variables, only available during execution. Refresh when
        execution finishes
        """
        self.__ff_run_temp_kwargs__: dict[str, Any] = {}  # temp run kwargs
        self._ff_in_run: bool = False  # whether the pipeline is in the run process
        self._ff_prefix: str = ""  # only root node has prefix as empty ""
        self._ff_name: str = ""  # only root node has name as empty ""
        self._ff_run_id: str = ""  # the current run id
        self._ff_flow_name: str = ""  # the run name
        self._ff_childs_called: dict = {}  # only available for root

    def __rshift__(self, other: Function) -> SequentialFunction:
        """Return a sequential function"""
        if isinstance(other, SequentialFunction):
            return SequentialFunction(funcs=[self, *other.funcs])
        if isinstance(self, SequentialFunction):
            return SequentialFunction(funcs=[*self.funcs, other])
        if not isinstance(other, Function):
            raise ValueError(
                f"Can only chain Function, but receive type: {other.__class__.__name__}"
            )
        return SequentialFunction(funcs=[self, other])

    def __floordiv__(self, other: Function) -> ConcurrentFunction:
        """Return a sequential function"""
        if isinstance(other, ConcurrentFunction):
            return ConcurrentFunction(funcs=[self, *other.funcs])
        if isinstance(self, ConcurrentFunction):
            return ConcurrentFunction(funcs=[*self.funcs, other])
        if not isinstance(other, Function):
            raise ValueError(
                f"Can only chain Function, but receive type: {other.__class__.__name__}"
            )
        return ConcurrentFunction(funcs=[self, other])

    def abs_pathx(self) -> str:
        """Get the node absolute path in execution flow.

        Note: only available during execution

        Path to node is similar to path to folder:
            .: root node
            .a: to node a
            .a.a1.a2: travel from root node to node a2

        Returns:
            str: absolute path of the node
        """
        if self._ff_prefix == ".":
            return f".{self._ff_name}"

        return f"{self._ff_prefix}.{self._ff_name}"

    def namex(self) -> str:
        """Name of the execution flow"""
        return self._ff_flow_name

    def idx(self) -> str:
        """Return execution id"""
        return self._ff_run_id

    def qualidx(self) -> str:
        """Return the qualified execution ids for this node"""
        return f"{self.namex()}|{self.idx()}|{self.abs_pathx()}"

    def parent_qualidx(self) -> str:
        """Return the qualified execution ids for the parent node"""
        return f"{self.namex()}|{self.idx()}|{self._ff_prefix}"

    def flow_qualidx(self):
        """Return the qualified execution flow id"""
        return f"{self.namex()}|{self.idx()}"

    def _runx(self, *args, **kwargs):
        """Subclass to handle pre- and post- run"""
        self._ff_in_run = True
        return self.run(*args, **kwargs)

    def _initialize_nodes(self):
        pass

    @abstractmethod
    def run(self, *args, **kwargs):  # type: ignore
        raise NotImplementedError(f"Please implement {self.__class__.__name__}.run")

    def __call__(self, *args, **kwargs):
        """Run the flow, accepting extra parameters for routing purpose"""
        if not hasattr(self, "_ff_initializing"):
            self._initialize()

        if _ff_run_kwargs := kwargs.pop("_ff_run_kwargs", {}):
            # TODO: another option is to communicate through context,
            # because this is run-time parameter, it will not be persisted in the
            # child nodes.
            self.set_run(_ff_run_kwargs, temp=True)

        if not self._ff_prefix:  # only root node has prefix as empty
            # administrative setup
            self._ff_run_id = self.config.run_id
            self._ff_flow_name = self.config.function_name
            self.context.create_context(context=self.flow_qualidx())
            self.context.set("run_id", self._ff_run_id, context=self.flow_qualidx())

            # publish parameters to the shared cache
            if self.config.params_publish:
                self.context.create_context(
                    context=f"{self.flow_qualidx()}|published_params",
                )
                for k, v in self.params.items():
                    self.context.set(
                        name=k,
                        value=v,
                        context=f"{self.flow_qualidx()}|published_params",
                    )
                for k, v in self._attrx["AllowExtraParam"].items():
                    self.context.set(
                        name=k,
                        value=v,
                        context=f"{self.flow_qualidx()}|published_params",
                    )

        self.context.create_context(context=self.qualidx(), exist_ok=True)

        if self.__ff_run_kwargs__:
            kwargs.update(self.__ff_run_kwargs__)

        if self.__ff_run_temp_kwargs__:
            kwargs.update(self.__ff_run_temp_kwargs__)

        try:
            output = (
                self._middleware(*args, **kwargs)
                if self._middleware
                else self._runx(*args, **kwargs)
            )

            if not self._ff_prefix:  # only root node has prefix as empty
                if self.config.params_publish:
                    self.context.clear(
                        None,
                        context=f"{self.flow_qualidx()}|published_params",
                    )
        except Exception as e:
            raise e from None
        finally:
            self._variablex()

        return output

    def __repr__(self):
        kwargs = ", ".join(
            [f"{key}={repr(getattr(self, key, None))}" for key in self._ff_params]
        )
        return f"{self.__class__.__name__}({kwargs})"

    def __str__(self):
        """Represent hierarchical structure of the Function"""
        if self._ff_nodes:
            kwargs = []
            for key in reversed(self._ff_nodes):
                value = str(getattr(self, key, None))
                value = value.replace("\n", "\n  ")
                kwargs.append(f"  ({key}): {value}")
            kwargs_repr = "\n".join(kwargs)
            return f"{self.__class__.__name__}(\n{kwargs_repr}\n)"

        kwargs = []
        for key in self._ff_params:
            value = str(getattr(self, key, None))
            if len(value) > 20:
                value = f"{value[:15]}..."
            kwargs.append(f"{key}={value}")
        kwargs_repr = ", ".join(kwargs)
        return f"{self.__class__.__name__}({kwargs_repr})"

    def _get_context(self) -> Context | None:
        return self._ff_context

    def _set_context(self, context: Context) -> None:
        self._ff_context = context
        for node in self._ff_nodes:
            if isinstance(getattr(self, node), Function):
                getattr(self, node).context = context

    def _del_context(self) -> None:
        del self._ff_context

    context = property(_get_context, _set_context, _del_context)

    @property
    def nodes(self) -> list[str]:
        return self._ff_nodes

    @property
    def params(self) -> dict[str, Any]:
        params = {}
        for key in self._ff_params:
            try:
                params[key] = getattr(self, key)
            except Exception:
                params[key] = None
        return params

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            return super().__setattr__(name, value)

        if name in self._ff_nodes:
            if not isinstance(value, Function):
                value = self._make_composable(value)
        elif name not in self._ff_params and name not in self._protected_keywords():
            if self.config.allow_extra:
                self._attrx["AllowExtraParam"][name] = value
            else:
                raise AttributeError(
                    f"Attribute {name} is not defined in {self.__class__.__name__}"
                )

        return super().__setattr__(name, value)

    def _initialize(self):
        if self._ff_context is None:
            self._ff_context = deserialize(settings.CONTEXT, safe=False)

        if not hasattr(self, "_ff_init_called"):
            raise RuntimeError(
                "Please call super().__init__(**params) in your __init__ method"
            )

        self._ff_initializing = True
        self._initialize_nodes()
        self._ff_initializing = False

    @classmethod
    def _collect_registered_params_and_nodes(cls) -> tuple[list[str], list[str]]:
        """Return the list of all params and nodes registered in the Function

        Returns:
            tuple[list[str], list[str]]: params, nodes
        """
        params, nodes = [], []

        for attr in dir(cls):
            if isinstance(getattr(cls, attr), NodeAttr):
                nodes.append(attr)
            elif isinstance(getattr(cls, attr), ParamAttr):
                params.append(attr)

        return list(sorted(set(params))), list(sorted(set(nodes)))

    @classmethod
    @lru_cache
    def _protected_keywords(cls) -> dict[str, type]:
        """Return the protected keywords and the class that defines each of them

        This method will concatenate the `_keywords` of all classes in the mro.
        """
        keywords = {}
        for each_cls in cls.mro():
            for keyword in getattr(each_cls, "__dict__", {}).get("_keywords", []):
                if keyword in keywords:
                    continue
                keywords[keyword] = each_cls
        return keywords

    def _make_composable(self, value) -> Function:
        return ProxyFunction(ff_original_obj=value)

    def _prepare_child(self, child: Function, name: str):
        if self._ff_in_run and self._track_child:
            child._ff_prefix = self.abs_pathx()
            child._ff_name = (
                name
                if name not in self._ff_childs_called
                else f"{name}[{self._ff_childs_called[name]}]"
            )
            child._ff_run_id = self._ff_run_id
            child._ff_flow_name = self._ff_flow_name
            self._ff_childs_called[name] = self._ff_childs_called.get(name, 0) + 1
            child.context = self.context

    @classmethod
    def visualize(cls):
        # 1 re-initialize the flow with different mode
        # 2 check the argument defintion passed into `run`
        # 3 run the flow with the fake argument
        # 4 track the graph
        return trace_pipelne_run(cls)

    @classmethod
    def withx(cls, **kwargs) -> Any:  # hacky way to make mypy happy
        """Return lazy init object that has the supplied params as default

        Args:
            kwargs: the keywords and params to be set as default

        Returns:
            A new Function with the supplied keywords and params set as default
        """
        return ObjectInitDeclaration(cls, **kwargs)

    def apply(self, fn: Callable):
        """Apply a function recursively to all nodes in a pipeline"""
        for node in self._ff_nodes:
            getattr(self, node).apply(fn)
        fn(self)
        return self

    def set(self, kwargs: dict, strict: bool = False):
        """Set the keyword arguments in the composable"""
        kwargs = unflatten_dict(kwargs)
        for name, value in kwargs.items():
            name = name.strip(".")
            if name in self._ff_nodes and isinstance(value, dict):
                getattr(self, name).set(value, strict=strict)
            else:
                try:
                    setattr(self, name, value)
                except Exception as e:
                    if strict:
                        raise e from None

    def set_run(self, kwargs: dict, temp=False):
        """Set run keyword arguments

        # TODO: should utilize context or queue to store these parameters, since the
        # same node object can be used in multiple pipelines, or also can be used
        # multiple times in the same pipeline. Hence, setting and clearing the
        # internal attributes will override the internal attributes of the same node
        # used in other pipelines / other parts of the pipeline.

        # It's tolerable for `set` though, because `set` deals with initialization
        # parameters, which will need to be the same.

        # Another approach is to force clone of node in a pipeline, so that changing
        # internal attribute of the node will never affect "that node" in other
        # pipelines.

        # Nevertheless, a good abstraction of the context will provide much
        # versatility to the users.
        """
        kwargs = unflatten_dict(kwargs)
        for name, value in kwargs.items():
            name = name.strip(".")
            if name in self._ff_nodes and isinstance(value, dict):
                getattr(self, name).set_run(value, temp=temp)
            else:
                if temp:
                    self.__ff_run_temp_kwargs__[name] = value
                else:
                    self.__ff_run_kwargs__[name] = value

    @classmethod
    def describe(cls) -> dict:
        """Describe the flow

        TODO: export the route of the flow as well
        """
        params, nodes = {}, {}

        for attr in dir(cls):
            attr_value = getattr(cls, attr)
            if isinstance(attr_value, NodeAttr):
                value = attr_value.__persist_flow__()
                if isinstance(
                    attr_value._default, ObjectInitDeclaration
                ) and issubclass(attr_value._default.cls, Function):
                    value["default"] = attr_value._default.cls.describe()  # type:ignore
                    value["default_kwargs"] = {
                        key: value
                        for key, value in attr_value._default.params.items()
                        if not isinstance(value, ObjectInitDeclaration)
                    }
                nodes[attr] = value
            elif isinstance(attr_value, ParamAttr):
                params[attr] = attr_value.__persist_flow__()

        return {
            "type": f"{cls.__module__}.{cls.__qualname__}",
            "params": params,
            "nodes": nodes,
        }

    def dump(self, ignore_depends: bool = True, strict: bool = True) -> dict:
        """Export the flow to a dictionary

        This method largely follows `theflow.utils.modules.serialize`, with the added
        options to modify the behavior of serialization.

        Args:
            ignore_depends: whether to ignore params and nodes that depend on others
            strict: whether to raise error if any param or node cannot be serialized
        """
        nodes: dict = {}
        for node in self._ff_nodes:
            try:
                obj: Function = getattr(self, node)
                if self.specs(node).get("depends_on", []) and ignore_depends:
                    continue
                nodes[node] = obj.dump(ignore_depends=ignore_depends, strict=strict)
            except Exception as e:
                if strict:
                    raise e from None
                logger.warn(e)
                nodes[node] = None

        params = {}
        for name, value in self.params.items():
            if self.specs(name).get("depends_on", []) and ignore_depends:
                continue
            try:
                params[name] = serialize(value)
            except ValueError as e:
                if strict:
                    raise e from None
                logger.warn(e)

        return {
            "__type__": f"{self.__module__}.{self.__class__.__qualname__}",
            **params,
            **nodes,
        }

    def specs(self, path: str) -> dict:
        """Get specification about a param or a node

        Args:
            path: the path to the node or param (.) delimited

        Returns:
            the specification of the param or node
        """
        path = path.strip(".")

        if "." in path:
            module, subpath = path.split(".", 1)
            return getattr(self, module).specs(subpath)

        definition = getattr(self.__class__, path)
        if not isinstance(definition, (ParamAttr, NodeAttr)):
            raise ValueError(f"{path} is not a param or a node")

        return definition.to_dict()

    def getx(self, path: str) -> Any:
        """Get the Function node or param based on path"""
        path = path.strip(".")
        if "." in path:
            module, subpath = path.split(".", 1)
            return getattr(self, module).getx(subpath)

        return getattr(self, path)

    def missing(self) -> dict[str, list[str]]:
        """Return the list of missing params and nodes"""
        params, nodes = [], []
        for attr in self._ff_params:
            if getattr(self.__class__, attr)._depends_on:
                continue
            try:
                getattr(self, attr)
            except Exception:
                params.append(attr)

        for attr in self._ff_nodes:
            if getattr(self.__class__, attr)._depends_on:
                continue
            try:
                child = getattr(self, attr)
                missings = child.missing()
                for each in missings["params"]:
                    params.append(f"{attr}.{each}")
                for each in missings["nodes"]:
                    nodes.append(f"{attr}.{each}")
            except Exception:
                nodes.append(attr)

        return {"params": params, "nodes": nodes}

    def get_from_path(self, path) -> Any:
        """Get a node or param by path, with tracking disabled

        Args:
            path: the path to the node or param (.) delimited

        Returns:
            Node or param, depending on the path
        """
        self._track_child = False
        path = path.strip(".")

        if "." in path:
            module, subpath = path.split(".", 1)
            obj = getattr(self, module)
            self._track_child = True
            return obj.get_from_path(subpath)

        obj = getattr(self, path)
        self._track_child = True
        return obj

    def is_compatible(self, path, obj) -> bool:
        """Check if the interface of a sample is compatible with the declared interface

        Args:
            path: the path to the node or param (.) delimited
            obj: the class or object to be checked

        Returns:
            True if compatible, False otherwise
        """
        specs = self.specs(path)
        func = obj
        if isinstance(obj, Function):
            func = obj.run
        elif isinstance(obj, type) and issubclass(obj, Function):
            func = obj.run

        if specs["__type__"] == "theflow.base.ParamAttr":
            return isinstance(obj, specs["type"])
        elif specs["__type__"] == "theflow.base.NodeAttr":
            reference_input = specs["input"]
            reference_output = specs["output"]
            target_input = input_signature(func)
            target_output = output_signature(func)

            ok_input, ok_output = False, False
            if reference_input == unset:
                ok_input = True
            else:
                for name, annot in reference_input.items():
                    if name not in target_input:
                        ok_input = False
                        break
                    ok_input = is_compatible_with(target_input[name], annot)
                    if not ok_input:
                        break

            if reference_output == unset:
                ok_output = True
            else:
                ok_output = is_compatible_with(target_output, reference_output)
            return ok_input and ok_output

        raise ValueError(f"{path} is not a param or a node")

    def log_progress(self, name: str | None = None, **kwargs):
        """Log the progress to the name"""
        if name is None:
            name = self.abs_pathx()

        run_tracker = RunTracker(self)
        run_tracker.log_progress(name, **kwargs)

    def __persist_flow__(self) -> dict:
        """Represent the flow in a JSON-serializable dictionary, that can be
        constructed
        """
        export: dict = {
            "__type__": f"{self.__module__}.{self.__class__.__qualname__}",
        }

        for name, value in self.params.items():
            if self.specs(name).get("depends_on", []):
                continue
            try:
                export[name] = serialize(value)
            except ValueError as e:
                logger.warn(e)
                continue

        for name in self._ff_nodes:
            if self.specs(name).get("depends_on", []):
                continue
            node = getattr(self, name).__persist_flow__()
            export[name] = node

        return export


class SessionFunction(Function):
    """Handle sesssion"""

    def start_session(self):
        if not hasattr(self, "_ff_initializing"):
            self._initialize()

        if not self._ff_prefix:  # only root node has prefix as empty
            # administrative setup
            self._ff_run_id = self.config.run_id
            self._ff_flow_name: str = self.config.function_name
            self.context.create_context(context=self.flow_qualidx())
            self.context.set("run_id", self._ff_run_id, context=self.flow_qualidx())

        self.context.create_context(context=self.qualidx(), exist_ok=True)

    def __call__(self, *args, **kwargs):
        if _ff_run_kwargs := kwargs.pop("_ff_run_kwargs", {}):
            # TODO: another option is to communicate through context,
            # because this is run-time parameter, it will not be persisted in the
            # child nodes.
            self.set_run(_ff_run_kwargs, temp=True)

        if self.__ff_run_kwargs__:
            kwargs.update(self.__ff_run_kwargs__)

        if self.__ff_run_temp_kwargs__:
            kwargs.update(self.__ff_run_temp_kwargs__)

        output = (
            self._middleware(*args, **kwargs)
            if self._middleware
            else self._runx(*args, **kwargs)
        )

        return output

    def end_session(self):
        self._variablex()


class ProxyFunction(Function):
    """Wrap an object to be a step.

    `ProxyFunction` demonstrates the same behavior as `Step`. The only difference is
    that `ProxyFunction` doesn't know how the object will be called (e.g. `__call__`
    or any methods) so it lazily exposes the methods when called.

    Cannot use this class directly because Function reserves some common _keywords
    that can conflict with original object.

    Raise ValueError in case of conflict.
    """

    ff_original_obj: Callable

    def __init__(self, **params):
        super().__init__(**params)
        if isinstance(self.ff_original_obj, ProxyFunction):
            raise ValueError(
                "Unnecessary to wrap a ProxyFunction object with ProxyFunction"
            )

    def _create_callable(self, callable_obj):
        def wrapper(*args, **kwargs):
            # TODO: after remove _ff_name from kwargs, we might be able to remove this
            # wrapper
            return callable_obj(*args, **kwargs)

        middleware_section: str = self.config.middleware_section
        middleware_setting = settings.MIDDLEWARE
        if middleware_section not in middleware_setting:
            raise ValueError(
                f'Middleware section "{middleware_section}" not found in settings'
            )
        middleware_switches = self.config.middleware_switches

        if middlware_cfg := middleware_setting[middleware_section]:
            next_call = wrapper
            for cls_name in reversed(middlware_cfg):
                if not middleware_switches.get(cls_name, True):
                    continue
                cls = import_dotted_string(cls_name, safe=False)
                next_call = cls(obj=self, next_call=next_call)
            return next_call

        return wrapper

    def __call__(self, *args, **kwargs):
        if self._ff_context is None:
            self._ff_context = deserialize(settings.CONTEXT, safe=False)

        return self._create_callable(getattr(self.ff_original_obj, "__call__"))(
            *args, **kwargs
        )

    def __getattr__(self, name):
        if "ff_original_obj" not in self._ff_params:
            raise AttributeError(
                f"{self.__class__.__qualname__} object has no attribute {name}"
            )

        if self._ff_context is None:
            self._ff_context = deserialize(settings.CONTEXT, safe=False)

        attr = getattr(self.ff_original_obj, name)
        if callable(attr):
            attr = self._create_callable(attr)
        return attr

    def run(self, *args, **kwargs) -> Any:
        if hasattr(self.ff_original_obj, "run") and callable(self._ff_original_obj.run):
            return self.ff_original_obj.run(*args, **kwargs)
        raise NotImplementedError(f"{self.ff_original_obj}.run doesn't exist")


class SequentialFunction(Function):
    """Sequential functions"""

    funcs: list[Function] = []

    def __len__(self):
        return len(self.funcs)

    def __getitem__(self, idx):
        return self.funcs[idx]

    def run(self, arg):
        for idx, func in enumerate(self.funcs):
            self._prepare_child(func, f"func{idx}_{func.__class__.__name__}")
            arg = func(arg)
        return arg


class ConcurrentFunction(Function):
    """Run functions concurrently"""

    funcs: list[Function] = []

    def __len__(self):
        return len(self.funcs)

    def __getitem__(self, idx):
        return self.funcs[idx]

    def run(self, arg):
        output = []
        for idx, func in enumerate(self.funcs):
            self._prepare_child(func, f"func{idx}_{func.__class__.__name__}")
            output.append(func(arg))
        return output
