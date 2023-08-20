"""Define base pipeline functionalities that underly both pipeline and step"""
import inspect
import logging
from copy import deepcopy
from collections import defaultdict
from functools import lru_cache
from typing import Any, Callable, Optional, _UnionGenericAlias, ForwardRef, Type, Union

from .config import Config, ConfigProperty
from .context import BaseContext, SimpleMemoryContext
from .visualization import trace_pipelne_run
from .utils import reindent_docstring


logger = logging.getLogger(__name__)


def contains_composable_in_annotation(annotation) -> bool:
    """Return True if the annotation contains Composable"""
    if isinstance(annotation, _UnionGenericAlias):
        return any(contains_composable_in_annotation(a) for a in annotation.__args__)
    if isinstance(annotation, ForwardRef):
        annotation = annotation._evaluate(globals(), locals(), frozenset())
        return contains_composable_in_annotation(annotation)
    if isinstance(annotation, type):
        return issubclass(annotation, Composable)
    return False


def flatten_dict(indict: dict) -> dict:
    """Flatten nested dict into 1-level dict

    Example:
        >>> flatten_dict({"a": {"b": 1}, "c": 2})
        {"a.b": 1, "c": 2}

    Args:
        indict: input dict

    Returns:
        flattened dict
    """
    outdict = {}
    for key, value in indict.items():
        if isinstance(value, dict):
            for subkey, subvalue in flatten_dict(value).items():
                outdict[f"{key}.{subkey}"] = subvalue
        else:
            outdict[key] = value
    return outdict


def unflatten_dict(indict: dict) -> dict:
    """Unflatten 1-level dict into nested dict

    Example:
        >>> unflatten_dict({"a.b": 1, "c": 2})
        {"a": {"b": 1}, "c": 2}

    Args:
        indict: input dict

    Returns:
        unflattened dict
    """
    outdict = {}
    for key, value in indict.items():
        subkeys = key.split(".")
        subdict = outdict
        for subkey in subkeys[:-1]:
            if subkey not in subdict:
                subdict[subkey] = {}
            subdict = subdict[subkey]
        subdict[subkeys[-1]] = value
    return outdict


class _BLANK_VALUE:
    pass


_blank = _BLANK_VALUE()


class Param:
    """Control the behavior of a parameter in a Composable

    Args:
        default: default value of the parameter
        default_callback: callback function to generate the default value. This
            callback takes in the Composable object and output the default value.
        refresh_on_set: if True, the original object will be refreshed when it is set
    """

    def __init__(
        self,
        default: Any = _blank,
        default_callback: Optional[
            Callable[[Optional["Composable"], Optional[Type["Composable"]]], Any]
        ] = None,
        help: str = "",
        refresh_on_set: bool = False,
        strict_type: bool = False,
        depends_on: Optional[Union[str, list[str]]] = None,
    ):
        self._default = default
        self._default_callback = default_callback
        self._help = help
        self._refresh_on_set = refresh_on_set
        self._strict_type = strict_type
        self._type = None

        if isinstance(depends_on, str):
            depends_on = [depends_on]
        self._depends_on: Optional[list[str]] = depends_on
        if self._depends_on and not self._default_callback:
            raise ValueError(
                f"If depends_on is set, default_callback must be provided to compute the value: {self._name}"
            )

    def __get__(
        self, obj: Optional["Composable"], type_: Optional[Type["Composable"]] = None
    ) -> Any:
        if obj is None:
            if self._default_callback:
                return self._default_callback(obj, type_)
            if isinstance(self._default, _BLANK_VALUE):
                raise AttributeError(
                    f"Parameter {self._name} is not set and has no default value"
                )
            return self._default

        if not isinstance(obj, Composable):
            raise ValueError("Param can only be used with Composable")

        if self._depends_on:
            self._calculate_from_depends_on(obj, type_)
        elif self._name not in obj.__ff_params__:
            if self._default_callback:
                value = self._default_callback(obj, type_)
            elif not isinstance(self._default, _BLANK_VALUE):
                value = self._default
            else:
                raise AttributeError(
                    f"Parameter {self._name} is not set and has no default value"
                )
            # TODO: need type checking of default value
            obj.__ff_params__[self._name] = value

        return obj.__ff_params__[self._name]

    def _calculate_from_depends_on(
        self, obj: "Composable", type_: Optional[Type["Composable"]] = None
    ):
        """Calculate the value of the parameter from the depends_on"""
        if not self._depends_on:
            return

        ids = {}
        for target in self._depends_on:
            old_id = obj.__ff_depends__[self._name].get(target, -1)
            new_id = id(getattr(obj, target))
            ids[target] = new_id
            if old_id != new_id:
                if self._default_callback is None:
                    raise ValueError(
                        f"Parameter {self._name} depends on {self._depends_on} "
                        "is a computed param and require default_callback"
                    )
                value = self._default_callback(obj, type_)
                obj.__ff_params__[self._name] = value
                for target_ in self._depends_on:
                    if target_ in ids:
                        obj.__ff_depends__[self._name][target_] = ids[target_]
                    else:
                        obj.__ff_depends__[self._name][target_] = id(
                            getattr(obj, target_)
                        )
                break

    def __set__(self, obj: "Composable", value: Any):
        if self._depends_on:
            raise ValueError(
                f"Parameter {self._name} depends on {self._depends_on}, cannot be set directly"
            )

        if self._strict_type:
            if not isinstance(value, obj.__dict__["__annotations__"][self._name]):
                # TODO: more sophisicated type checking (e.g. handle Union, Optional...)
                raise ValueError(
                    f"Value {value} is not of type {type(self._default)} for parameter {self._name}"
                )

        obj.__ff_params__[self._name] = value
        if self._refresh_on_set:
            obj._initialize()

    def __delete__(self, obj: "Composable"):
        if self._name in obj.__ff_params__:
            del obj.__ff_params__[self._name]
            if self._refresh_on_set:
                obj._initialize()

    def __set_name__(self, owner, name):
        self._name = name
        self._owner = owner


class Node:
    """Control the behavior of a node in a Composable"""

    def __init__(
        self,
        default: Union[_BLANK_VALUE, Type["Composable"]] = _blank,
        default_kwargs: Optional[dict[str, Any]] = None,
        default_callback: Optional[
            Callable[
                [Optional["Composable"], Optional[Type["Composable"]]], "Composable"
            ]
        ] = None,
        depends_on: Optional[Union[str, list[str]]] = None,
        help: str = "",
        input: Union[_BLANK_VALUE, dict[str, Any]] = _blank,
        output: Any = _blank,
    ):
        self._default = default
        self._default_kwargs: dict = default_kwargs or {}
        self._default_callback = default_callback
        self._help = help
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        self._depends_on: Optional[list[str]] = depends_on

        self._input: Union[_BLANK_VALUE, dict[str, Any]] = input
        self._output: Any = output
        has_run_method = callable(getattr(default, "run", None))
        if self._input is _blank and has_run_method:
            type_annotation = deepcopy(default.run.__annotations__)  # type: ignore
            type_annotation.pop("return", None)
            if type_annotation:
                self._input = type_annotation
        if self._output is _blank and has_run_method:
            type_annotation = default.run.__annotations__.get("return")  # type: ignore
            if type_annotation:
                self._output = type_annotation

    def __get__(
        self, obj: Optional["Composable"], type_: Optional[Type["Composable"]] = None
    ) -> "Composable":
        if obj is None:
            if self._default_callback:
                return self._default_callback(obj, type_)
            if isinstance(self._default, _BLANK_VALUE):
                raise AttributeError(
                    f"Node {self._name} is not set and has no default value"
                )
            return self._default(**self._default_kwargs)

        if not isinstance(obj, Composable):
            raise ValueError("Node can only be used with Composable")

        if self._depends_on:
            self._calculate_from_depends_on(obj, type_)
        elif self._name not in obj.__ff_nodes__:
            if self._default_callback:
                value = self._default_callback(obj, type_)
            elif not isinstance(self._default, _BLANK_VALUE):
                value = self._default(**self._default_kwargs)
            else:
                raise AttributeError(
                    f"Node {self._name} is not set and has no default value"
                )

            obj.__ff_nodes__[self._name] = value

        return obj.__ff_nodes__[self._name]

    def _calculate_from_depends_on(
        self, obj: "Composable", type_: Optional[Type["Composable"]] = None
    ):
        """Calculate the value of the parameter from the depends_on"""
        if not self._depends_on:
            return

        ids = {}
        for target in self._depends_on:
            old_id = obj.__ff_depends__[self._name].get(target, -1)
            new_id = id(getattr(obj, target))
            ids[target] = new_id
            if old_id != new_id:
                if self._default_callback is None:
                    raise ValueError(
                        f"Parameter {self._name} depends on {self._depends_on} "
                        "is a computed param and require default_callback"
                    )
                value = self._default_callback(obj, type_)
                obj.__ff_nodes__[self._name] = value
                for target_ in self._depends_on:
                    if target_ in ids:
                        obj.__ff_depends__[self._name][target_] = ids[target_]
                    else:
                        obj.__ff_depends__[self._name][target_] = id(
                            getattr(obj, target_)
                        )
                break

    def __set__(self, obj: "Composable", value: "Composable"):
        if not isinstance(value, Composable):
            raise ValueError(
                f"Node can only be used with Composable, got {type(value)}"
            )

        obj.__ff_nodes__[self._name] = value

    def __delete__(self, obj: "Composable"):
        if self._name in obj.__ff_nodes__:
            del obj.__ff_nodes__[self._name]

    def __set_name__(self, owner, name):
        self._name = name
        self._owner = owner


def param(depends_on: Optional[Union[str, list[str]]] = None):
    def inner(func):
        return Param(
            default_callback=lambda obj, _: func(obj),
            help=reindent_docstring(func.__doc__),
            depends_on=depends_on,
        )

    return inner


def node(depends_on: Optional[Union[str, list[str]]] = None):
    def inner(func):
        return Node(
            default_callback=lambda obj, _: func(obj),
            help=reindent_docstring(func.__doc__),
            depends_on=depends_on,
        )

    return inner


class MetaComposable(type):
    def __new__(cls, clsname, bases, attrs):
        # Make sure all nodes and params have the Node and Param descriptor
        for name, value in attrs.get("__annotations__", {}).items():
            if name.startswith("_"):
                continue
            if name in attrs and isinstance(attrs[name], (Node, Param)):
                continue
            if contains_composable_in_annotation(value):
                desc = Node(default=attrs[name]) if name in attrs else Node()
            else:
                desc = Param(default=attrs[name]) if name in attrs else Param()
            attrs[name] = desc

        obj: Type["Composable"] = super().__new__(cls, clsname, bases, attrs)  # type: ignore

        # Raise invalid nodes and params
        for name, value in attrs.items():
            if not isinstance(value, (Node, Param)):
                continue
            if name.startswith("_"):
                raise ValueError(f"Node and param name cannot start with _: {name}")

            if name in obj._protected_keywords():
                raise ValueError(
                    f'"{name}" is a protected keyword, defined by '
                    f'"{obj._protected_keywords()[name]}"'
                )
        return obj


class Composable(metaclass=MetaComposable):
    """Base class that handle basic logic of a composable component

    Everything is a composable component. Subclass `Composable` to define and run your
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
    Composable is explicit.
    """

    class Middleware:
        middleware = [
            "theflow.middleware.TrackProgressMiddleware",
            "theflow.middleware.SkipComponentMiddleware",
        ]

    config = ConfigProperty()

    _keywords = [
        "last_run",
        "apply",
        "Middleware",
        "Config",
        "config",
        "run",
        "params",
        "prefix",
        "nodes",
        "context",
    ]

    def __init__(self, _params: Optional[dict] = None, /, **params):
        self.__ff_params__: dict[str, Any] = {}
        self.__ff_nodes__: dict[str, Composable] = {}
        self.__ff_depends__: dict[str, dict[str, int]] = defaultdict(dict)
        self.__ff_run_kwargs__: dict[str, Any] = {}
        self.__ff_run_temp_kwargs__: dict[str, Any] = {}
        self._ff_params: list[str] = []
        self._ff_nodes: list[str] = []
        self._ff_config: Optional[Config] = None
        self._ff_context: Optional[BaseContext] = None
        self._ff_prefix: Optional[str] = None  # only root node has prefix as None

        # collect
        self._ff_params, self._ff_nodes = self._collect_registered_params_and_nodes()

        self._ff_init_called = False
        if _params:
            self.set(_params)
        if params:
            self.set(params)
        self._ff_init_called = True

        self._ff_run_id: Optional[str] = None  # only available for root pipeline
        self._middleware = None
        if middlware_cfg := getattr(self, "Middleware"):
            from .utils import import_dotted_string

            next_call = self._run
            for cls_name in reversed(middlware_cfg.middleware):
                cls = import_dotted_string(cls_name)
                next_call = cls(obj=self, next_call=next_call)
            self._middleware = next_call

        if not hasattr(self, "_ff_initializing"):
            # TODO: this work better if we formulate config and context as independent
            self._initialize()

    def _run(self, *args, **kwargs):
        """Subclass to handle pre- and post- run"""
        kwargs.pop("_ff_name", None)
        return self.run(*args, **kwargs)

    def _initialize_nodes(self):
        pass

    def run(self, *args, **kwargs):  # type: ignore
        raise NotImplementedError(f"Please implement {self.__class__.__name__}.run")

    def __call__(self, *args, **kwargs):
        """Run the flow, accepting extra parameters for routing purpose"""
        if not hasattr(self, "_ff_initializing"):
            self._initialize()

        if _ff_run_kwargs := kwargs.pop("_ff_run_kwargs", {}):
            self.set_run(_ff_run_kwargs, temp=True)

        _ff_name = self._handle_step_name(kwargs.get("_ff_name", ""))
        if self._ff_prefix is None:  # only root node has prefix as None
            # administrative setup
            self._ff_run_id = self.config.run_id
            self.context.clear_all()
            self.context.set("run_id", self._ff_run_id, context=None)
            kwargs["_ff_name"] = _ff_name

        if _ff_name is not None:
            self.context.create_local_context(context=_ff_name, exist_ok=True)

        if self.__ff_run_kwargs__:
            kwargs.update(self.__ff_run_kwargs__)

        if self.__ff_run_temp_kwargs__:
            kwargs.update(self.__ff_run_temp_kwargs__)

        output = (
            self._middleware(*args, **kwargs)
            if self._middleware
            else self._run(*args, **kwargs)
        )
        self.__ff_run_temp_kwargs__.clear()
        return output

    def __repr__(self):
        kwargs = ", ".join(
            [f"{key}={repr(getattr(self, key, None))}" for key in self._ff_params]
        )
        return f"{self.__class__.__name__}({kwargs})"

    def __str__(self):
        return f"{self.__class__.__name__} (nodes: {self._ff_nodes})"

    def _get_context(self) -> BaseContext:
        if self._ff_context is None:
            raise ValueError("Context is not set")
        return self._ff_context

    def _set_context(self, context: BaseContext) -> None:
        self._ff_context = context
        for node in self._ff_nodes:
            if isinstance(getattr(self, node), Composable):
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
            except:
                params[key] = None
        return params

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            return super().__setattr__(name, value)

        if name in self.__class__._protected_keywords():
            return super().__setattr__(name, value)

        if name in self._ff_nodes:
            value = self._make_composable(value)

        try:
            return super().__setattr__(name, value)
        except Exception:
            raise ValueError(
                f"Cannot set {self.__class__}.{name} to {value}: param {name} not declared"
            )

    def _initialize(self):
        # TODO: move setting up config and context out of _initialize. They do not have
        # anything to do with initializing the nodes
        if self._ff_config is None:
            self._ff_config = Config(
                cls=self.__class__
            )  # TODO: this is more like setting than config
        if self._ff_context is None:
            self._ff_context = (
                SimpleMemoryContext()
            )  # TODO: connect/create the context from setting

        if not hasattr(self, "_ff_init_called"):
            raise RuntimeError(
                "Please call super().__init__(**params) in your __init__ method"
            )

        self._ff_initializing = True
        self._initialize_nodes()
        for node in self._ff_nodes:
            node_obj = getattr(self, node, None)
            if node_obj is not None:
                node_obj.config = self._ff_config
                node_obj.context = self._ff_context
        self._ff_initializing = False

    @classmethod
    def _collect_registered_params_and_nodes(cls) -> tuple[list[str], list[str]]:
        """Return the list of all params and nodes registered in the Composable

        Returns:
            tuple[list[str], list[str]]: params, nodes
        """
        params, nodes = [], []

        for each_cls in cls.mro():
            for attr, attr_value in each_cls.__dict__.items():
                if isinstance(attr_value, Node):
                    nodes.append(attr)
                elif isinstance(attr_value, Param):
                    params.append(attr)

        return list(sorted(set(params))), list(sorted(set(nodes)))

    @classmethod
    @lru_cache
    def _protected_keywords(cls) -> dict[str, type]:
        """Return the protected keywords and the class that defines each of them"""
        keywords = {}
        for each_cls in cls.mro():
            for keyword in getattr(each_cls, "__dict__", {}).get("_keywords", []):
                if keyword in keywords:
                    continue
                keywords[keyword] = each_cls
        return keywords

    def _make_composable(self, value) -> "Composable":
        if not isinstance(value, Composable):
            value = ComposableProxy(ff_original_obj=value)

        return value

    def _handle_step_name(self, _ff_name: str = "") -> str:
        """Combine the prefix and the step name, and pass it to the child steps.

        In case the step name is empty (default ""), the class name will be used
        instead. In the future, the step name can be dynamically constructed, based
        on:
            - the number of input args, the type of each of input args
            - the number of kwargs, the name of the kwargs, the type of each of the kwargs
            - whether a similar step name exists in the context

        Args:
            _ff_name: the step name passed in from __call__ argument

        Returns:
            the processed step name
        """
        if not isinstance(_ff_name, str):
            raise TypeError(f"_ff_name must be str, got {type(_ff_name)}")

        if self._ff_prefix is not None:
            if "." in _ff_name:
                raise AttributeError("_ff_name cannot contain `.`")
            if "*" in _ff_name:
                raise AttributeError("_ff_name cannot contain `*`")
            if not _ff_name:
                _ff_name = self.__class__.__name__

            _ff_name = ".".join([self._ff_prefix, _ff_name])

        for node in self._ff_nodes:
            setattr(getattr(self, node), "_ff_prefix", _ff_name)

        return _ff_name

    @classmethod
    def visualize(cls):
        # 1 re-initialize the flow with different mode
        # 2 check the argument defintion passed into `run`
        # 3 run the flow with the fake argument
        # 4 track the graph
        return trace_pipelne_run(cls)

    def apply(self, fn: Callable):
        """Apply a function recursively to all nodes in a pipeline"""
        for node in self._ff_nodes:
            getattr(self, node).apply(fn)
        fn(self)
        return self

    def set(self, kwargs: dict):
        kwargs = unflatten_dict(kwargs)
        for name, value in kwargs.items():
            if name in self._ff_nodes and isinstance(value, dict):
                getattr(self, name).set(value)
            else:
                setattr(self, name, value)

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
            if name in self._ff_nodes and isinstance(value, dict):
                getattr(self, name).set_run(value, temp=temp)
            else:
                if temp:
                    self.__ff_run_temp_kwargs__[name] = value
                else:
                    self.__ff_run_kwargs__[name] = value

    @classmethod
    def _describe(cls) -> dict:
        """Describe the pipeline fully, along with all the nodes and their parameters"""
        params, nodes = {}, {}

        for each_cls in cls.mro():
            for attr, attr_value in each_cls.__dict__.items():
                if isinstance(attr_value, Node) and attr not in nodes:
                    if attr_value._depends_on:
                        continue
                    value = None
                    if isinstance(attr_value._default, type) and issubclass(
                        attr_value._default, Composable
                    ):
                        value = attr_value._default._describe()
                    nodes[attr] = value
                elif isinstance(attr_value, Param) and attr not in params:
                    if attr_value._depends_on:
                        continue
                    try:
                        value = getattr(cls, attr)
                    except:
                        value = None
                    params[attr] = value

        return {
            "type": f"{cls.__module__}.{cls.__qualname__}",
            "params": params,
            "nodes": nodes,
        }

    def describe(self, original=False) -> dict:
        """Describe the pipeline, along with all the nodes and their parameters

        Args:
            original: if True, return the original description, otherwise return the
                description of the current state
        """
        if original:
            return self._describe()

        nodes = {}
        for node in self._ff_nodes:
            try:
                node_obj = getattr(self, node)
                nodes[node] = node_obj.describe()
            except:
                nodes[node] = None

        params = {}
        for name, value in self.params.items():
            if inspect.isfunction(value):
                value = f"{value.__module__}.{value.__qualname__}"
            params[name] = value

        return {
            "type": f"{self.__module__}.{self.__class__.__qualname__}",
            "params": params,
            "nodes": nodes,
        }

    def missing(self) -> dict[str, list[str]]:
        """Return the list of missing params and nodes"""
        params, nodes = [], []
        for attr in self._ff_params:
            if self.__class__.__dict__[attr]._depends_on:
                continue
            try:
                getattr(self, attr)
            except:
                params.append(attr)

        for attr in self._ff_nodes:
            if self.__class__.__dict__[attr]._depends_on:
                continue
            try:
                child = getattr(self, attr)
                missings = child.missing()
                for each in missings["params"]:
                    params.append(f"{attr}.{each}")
                for each in missings["nodes"]:
                    nodes.append(f"{attr}.{each}")
            except:
                nodes.append(attr)

        return {"params": params, "nodes": nodes}


class ComposableProxy(Composable):
    """Wrap an object to be a step.

    `ComposableProxy` demonstrates the same behavior as `Step`. The only difference is that
    `ComposableProxy` doesn't know how the object will be called (e.g. `__call__` or any
    methods) so it lazily exposes the methods when called.

    Cannot use this class directly because Composable reserves some common _keywords
    that can conflict with original object.

    Raise ValueError in case of conflict.
    """

    ff_original_obj: Callable

    def __init__(self, **params):
        super().__init__(**params)
        if isinstance(self.ff_original_obj, ComposableProxy):
            raise ValueError(
                "Unnecessary to wrap a ComposableProxy object with ComposableProxy"
            )

    def _create_callable(self, callable_obj):
        def wrapper(*args, **kwargs):
            kwargs.pop("_ff_name", None)
            return callable_obj(*args, **kwargs)

        if middlware_cfg := getattr(self, "Middleware"):
            from .utils import import_dotted_string

            next_call = wrapper
            for cls_name in reversed(middlware_cfg.middleware):
                cls = import_dotted_string(cls_name)
                next_call = cls(obj=self, next_call=next_call)
            return next_call

        return wrapper

    def run(self, *args, **kwargs):
        """Pass-through to the original object"""
        return self.ff_original_obj.run(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        if self._ff_config is None:
            self._ff_config = Config(cls=self.__class__)
        if self._ff_context is None:
            self._ff_context = SimpleMemoryContext()

        return self._create_callable(getattr(self.ff_original_obj, "__call__"))(
            *args, **kwargs
        )

    def __getattr__(self, name):
        if name.startswith("_"):
            return super().__getattr__(name)

        if "ff_original_obj" not in self._ff_params:
            raise AttributeError(
                f"{self.__class__.__qualname__} object has no attribute {name}"
            )

        if self._ff_config is None:
            self._ff_config = Config(cls=self.__class__)
        if self._ff_context is None:
            self._ff_context = SimpleMemoryContext()

        attr = getattr(self.ff_original_obj, name)
        if callable(attr):
            attr = self._create_callable(attr)
        return attr
