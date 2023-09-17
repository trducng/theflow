import logging
from abc import abstractmethod
from collections import defaultdict
from functools import lru_cache
from typing import (
    Any,
    Callable,
    Dict,
    ForwardRef,
    Generic,
    List,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
    cast,
)

from .config import Config, ConfigProperty
from .context import Context
from .exceptions import InvalidNodeDefinition, InvalidParamDefinition
from .runs.base import RunTracker
from .settings import settings
from .utils.modules import import_dotted_string, init_object, serialize
from .utils.pretties import reindent_docstring, unflatten_dict
from .utils.typings import (
    input_signature,
    is_compatible_with,
    is_union_type,
    output_signature,
)
from .visualization import trace_pipelne_run

logger = logging.getLogger(__name__)


def contains_composable_in_annotation(annotation) -> bool:
    """Return True if the annotation contains Compose"""
    if is_union_type(annotation):
        return any(contains_composable_in_annotation(a) for a in annotation.__args__)
    if isinstance(annotation, ForwardRef):
        annotation = annotation._evaluate(globals(), locals(), frozenset())
        return contains_composable_in_annotation(annotation)
    if isinstance(annotation, type):
        return issubclass(annotation, Compose)
    return False


class empty:
    pass


ParamAttribute = TypeVar("ParamAttribute")
NodeAttribute = TypeVar("NodeAttribute", bound="Compose")


class Param(Generic[ParamAttribute]):
    """Control the behavior of a parameter in a Compose

    Args:
        default: default value of the parameter
        default_callback: callback function to generate the default value. This
            callback takes in the Compose object and output the default value.
        refresh_on_set: if True, the original object will be refreshed when it is set
        depends_on: if set, the value of the parameter will be calculated from the
            values of the depends_on parameters (requires `default_callback`)
        no_cache: if True, the value of the parameter will not be cached and will be
            recalculated everytime it is accessed (requires `default_callback`)
    """

    def __init__(
        self,
        default: Union[ParamAttribute, Type["empty"]] = empty,
        default_callback: Optional[
            Callable[[Optional["Compose"], Optional[Type["Compose"]]], ParamAttribute]
        ] = None,
        help: str = "",
        refresh_on_set: bool = False,
        strict_type: bool = False,
        depends_on: Optional[Union[str, List[str]]] = None,
        no_cache: bool = False,
    ):
        self._default: ParamAttribute = cast(ParamAttribute, default)
        self._default_callback = default_callback
        self._help = help
        self._refresh_on_set = refresh_on_set
        self._strict_type = strict_type
        self._no_cache = no_cache
        self._type = None

        if isinstance(depends_on, str):
            depends_on = [depends_on]
        self._depends_on: Optional[List[str]] = depends_on

    def _validate_args(self):
        """Validate the __init__ args"""

        if self._depends_on and not self._default_callback:
            raise InvalidParamDefinition(
                "Must provide `default_callback` when param has `depends_on`: "
                f"{self._qual_name}"
            )
        if self._depends_on and self._no_cache:
            raise InvalidParamDefinition(
                "Cannot set `no_cache=True` if param has `depends_on`: "
                f"{self._qual_name}"
            )

    def __get__(
        self, obj: Optional["Compose"], type_: Optional[Type["Compose"]] = None
    ) -> ParamAttribute:
        if obj is None:
            if self._default_callback:
                return self._default_callback(obj, type_)
            if self._default == empty:
                raise AttributeError(
                    f"Parameter {self._name} is not set and has no default value"
                )
            return self._default

        if not isinstance(obj, Compose):
            raise ValueError("Param can only be used with Compose")

        if self._depends_on:
            self._calculate_from_depends_on(obj, type_)
        elif self._name not in obj.__ff_params__ or self._no_cache:
            if self._default_callback:
                value = self._default_callback(obj, type_)
            elif self._default != empty:
                value = self._default
            else:
                raise AttributeError(
                    f"Parameter {self._name} is not set and has no default value"
                )
            # TODO: need type checking of default value
            obj.__ff_params__[self._name] = value

        return obj.__ff_params__[self._name]

    def _calculate_from_depends_on(
        self, obj: "Compose", type_: Optional[Type["Compose"]] = None
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
                        f"Param {self._qual_name} depends on {self._depends_on} "
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

    def __set__(self, obj: "Compose", value: Any):
        if self._depends_on:
            raise ValueError(
                f"Param {self._qual_name} depends on {self._depends_on}, "
                "cannot be set directly"
            )

        if self._strict_type:
            if not isinstance(value, obj.__dict__["__annotations__"][self._name]):
                # TODO: more sophisicated type checking (e.g. handle Union, Optional...)
                raise ValueError(
                    f"Value {value} is not of type {type(self._default)} "
                    f"for parameter {self._name}"
                )

        obj.__ff_params__[self._name] = value
        if self._refresh_on_set:
            obj._initialize()

    def __delete__(self, obj: "Compose"):
        if self._name in obj.__ff_params__:
            del obj.__ff_params__[self._name]
            if self._refresh_on_set:
                obj._initialize()

    def __set_name__(self, owner: type, name: str):
        self._name = name
        self._owner = owner
        self._qual_name = (
            f"{self._owner.__module__}.{self._owner.__name__}.{self._name}"
        )

        # validate after receiving the name and type for actionable error message
        self._validate_args()

    @classmethod
    def decorate(cls, **kwargs):
        """Automatically set the `defeault_callback`"""
        if "default_callback" in kwargs:
            raise InvalidParamDefinition(
                "Redundant `default_callback` in Param.decorate: "
                f"({kwargs['default_callback']})"
            )

        def inner(func):
            help: str = kwargs.pop("help", reindent_docstring(func.__doc__))
            return cls(default_callback=lambda obj, _: func(obj), help=help, **kwargs)

        return inner

    def to_dict(self) -> dict:
        """Return the internal state of the Param as a dict"""
        return {
            "__type__": "param",
            "default": self._default,
            "default_callback": self._default_callback,
            "help": self._help,
            "refresh_on_set": self._refresh_on_set,
            "strict_type": self._strict_type,
            "depends_on": self._depends_on,
            "no_cache": self._no_cache,
        }

    def __persist_flow__(self):
        """Return the state in a way that can be initiated"""
        type_ = f"{self._owner.__module__}.{self._owner.__qualname__}"
        export: dict = {"__type__": type_}

        for key, value in self.to_dict().items():
            try:
                serialized = serialize(value)
            except Exception as e:
                logger.debug(f"{type_}.{self._name}.{key}: {e}... skip")
                serialized = serialize(empty)
            export[key] = serialized

        return export


class Node(Generic[NodeAttribute]):
    """Control the behavior of a node in a Compose"""

    def __init__(
        self,
        default: Union[Type["empty"], Type[NodeAttribute]] = empty,
        default_kwargs: Optional[Dict[str, Any]] = None,
        default_callback: Optional[
            Callable[[Optional["Compose"], Optional[Type["Compose"]]], NodeAttribute]
        ] = None,
        depends_on: Optional[Union[str, List[str]]] = None,
        no_cache: bool = False,
        help: str = "",
        input: Union[Type["empty"], Dict[str, Any]] = empty,
        output: Any = empty,
    ):
        self._default: Type[NodeAttribute] = cast(Type[NodeAttribute], default)
        self._default_kwargs: dict = default_kwargs or {}
        self._default_callback = default_callback
        self._help = help
        if isinstance(depends_on, str):
            depends_on = [depends_on]
        self._depends_on: Optional[List[str]] = depends_on
        self._no_cache = no_cache
        if self._depends_on and self._no_cache:
            raise ValueError(
                f"depends_on and no_cache cannot be both set: {self._name}"
            )

        self._input: Union[Type["empty"], Dict[str, Any]] = input
        self._output: Any = output

        has_run_method = callable(getattr(default, "run", None))
        if self._input == empty and has_run_method:
            self._input = input_signature(default.run)  # type: ignore
        if self._output == empty and has_run_method:
            self._output = output_signature(default.run)  # type: ignore

    def __get__(
        self, obj: Optional["Compose"], type_: Optional[Type["Compose"]] = None
    ) -> NodeAttribute:
        if obj is None:
            if self._default_callback:
                return self._default_callback(obj, type_)
            if self._default == empty:
                raise AttributeError(
                    f"Node {self._name} is not set and has no default value"
                )
            return self._default(**self._default_kwargs)

        if not isinstance(obj, Compose):
            raise ValueError("Node can only be used with Compose")

        if self._depends_on:
            self._calculate_from_depends_on(obj, type_)
        elif self._name not in obj.__ff_nodes__ or self._no_cache:
            if self._default_callback:
                value = self._default_callback(obj, type_)
            elif self._default != empty:
                value = self._default(**self._default_kwargs)
            else:
                raise AttributeError(
                    f"Node {self._name} is not set and has no default value"
                )

            obj.__ff_nodes__[self._name] = value

        obj._prepare_child(obj.__ff_nodes__[self._name], self._name)

        if not isinstance(obj.__ff_nodes__[self._name], Compose):
            raise ValueError(f"Node {obj.__class__}.{self._name} is not a Compose")

        return cast(NodeAttribute, obj.__ff_nodes__[self._name])

    def _calculate_from_depends_on(
        self, obj: "Compose", type_: Optional[Type["Compose"]] = None
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

    def __set__(self, obj: "Compose", value: NodeAttribute):
        if not isinstance(value, Compose):
            raise ValueError(f"Node can only be used with Compose, got {type(value)}")

        obj.__ff_nodes__[self._name] = value

    def __delete__(self, obj: "Compose"):
        if self._name in obj.__ff_nodes__:
            del obj.__ff_nodes__[self._name]

    def __set_name__(self, owner, name):
        self._name = name
        self._owner = owner

    @classmethod
    def decorate(cls, **kwargs):
        """Automatically set the `defeault_callback`"""
        if "default_callback" in kwargs:
            raise InvalidNodeDefinition(
                "Redundant `default_callback` in Node.decorate: "
                f"({kwargs['default_callback']})"
            )

        def inner(func):
            help: str = kwargs.pop("help", reindent_docstring(func.__doc__))
            return cls(default_callback=lambda obj, _: func(obj), help=help, **kwargs)

        return inner

    def to_dict(self) -> dict:
        """Return the internal state of a node as dict"""
        return {
            "type": "node",
            "default": self._default,
            "default_kwargs": self._default_kwargs,
            "default_callback": self._default_callback,
            "help": self._help,
            "depends_on": self._depends_on,
            "no_cache": self._no_cache,
            "input": self._input,
            "output": self._output,
        }

    def __persist_flow__(self):
        """Return the state in a way that can be initiated"""
        type_ = f"{self._owner.__module__}.{self._owner.__qualname__}"
        export: dict = {"__type__": type_}

        for key, value in self.to_dict().items():
            try:
                serialized = serialize(value)
            except Exception as e:
                logger.debug(f"{type_}.{self._name}.{key}: {e}... skip")
                serialized = serialize(empty)
            export[key] = serialized

        return export


class MetaCompose(type):
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

        try:
            obj: Type["Compose"] = super().__new__(
                cls, clsname, bases, attrs  # type: ignore
            )
        except Exception as e:
            cause = getattr(e, "__cause__", None)
            if isinstance(cause, InvalidParamDefinition):
                raise cause from None
            raise e from None

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


class Compose(metaclass=MetaCompose):
    """Base class that handle basic logic of a composable component

    Everything is a composable component. Subclass `Compose` to define and run your
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
    Compose is explicit.
    """

    class Middleware:
        middleware = [
            "theflow.middleware.TrackProgressMiddleware",
            "theflow.middleware.SkipComponentMiddleware",
        ]

    config = ConfigProperty()

    _keywords = [
        "Middleware",
        "Config",
        "abs_pathx",
        "apply",
        "config",
        "context",
        "describe",
        "dump",
        "flow_qualidx",
        "get_from_path",
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
    ]

    def __init__(self, _params: Optional[dict] = None, /, **params):
        self.last_run: RunTracker
        self.__ff_params__: Dict[str, Any] = {}
        self.__ff_nodes__: Dict[str, Compose] = {}
        self.__ff_depends__: Dict[str, Dict[str, int]] = defaultdict(dict)
        self.__ff_run_kwargs__: Dict[str, Any] = {}
        self._ff_params: List[str] = []
        self._ff_nodes: List[str] = []
        self._ff_config: Config = Config(cls=self.__class__)
        self._ff_context: Optional[Context] = None

        # collect
        self._ff_params, self._ff_nodes = self._collect_registered_params_and_nodes()

        self._ff_init_called = False
        if _params:
            self.set(_params)
        if params:
            self.set(params)
        self._ff_init_called = True

        self._middleware = None
        if middlware_cfg := getattr(self, "Middleware"):
            next_call = self._run
            for cls_name in reversed(middlware_cfg.middleware):
                # TODO: handle safe import
                cls = import_dotted_string(cls_name, safe=False)
                next_call = cls(obj=self, next_call=next_call)
            self._middleware = next_call

        if not hasattr(self, "_ff_initializing"):
            # TODO: this work better if we formulate config and context as independent
            self._initialize()

        # Initialize temporary execution variables
        self._variablex()

    def _variablex(self):
        """Set temporary variables, only available during execution. Refresh when
        execution finishes
        """
        self.__ff_run_temp_kwargs__: Dict[str, Any] = {}  # temp run kwargs
        self._ff_in_run: bool = False  # whether the pipeline is in the run process
        self._ff_prefix: str = ""  # only root node has prefix as empty ""
        self._ff_name: str = ""  # only root node has name as empty ""
        self._ff_run_id: str = ""  # the current run id
        self._ff_flow_name: str = ""  # the run name
        self._ff_childs_called: dict = {}  # only available for root

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

    def _run(self, *args, **kwargs):
        """Subclass to handle pre- and post- run"""
        # TODO: can remove self._run
        return self.run(*args, **kwargs)

    def _initialize_nodes(self):
        pass

    @abstractmethod
    def run(self, *args, **kwargs):  # type: ignore
        raise NotImplementedError(f"Please implement {self.__class__.__name__}.run")

    def __call__(self, *args, **kwargs):
        """Run the flow, accepting extra parameters for routing purpose"""
        self._ff_in_run = True

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
            self._ff_flow_name: str = self.config.compose_name
            self.context.create_context(context=self.flow_qualidx())
            self.context.set("run_id", self._ff_run_id, context=self.flow_qualidx())

        self.context.create_context(context=self.qualidx(), exist_ok=True)

        if self.__ff_run_kwargs__:
            kwargs.update(self.__ff_run_kwargs__)

        if self.__ff_run_temp_kwargs__:
            kwargs.update(self.__ff_run_temp_kwargs__)

        try:
            output = (
                self._middleware(*args, **kwargs)
                if self._middleware
                else self._run(*args, **kwargs)
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
        return f"{self.__class__.__name__} (nodes: {self._ff_nodes})"

    def _get_context(self) -> Optional[Context]:
        return self._ff_context

    def _set_context(self, context: Context) -> None:
        self._ff_context = context
        for node in self._ff_nodes:
            if isinstance(getattr(self, node), Compose):
                getattr(self, node).context = context

    def _del_context(self) -> None:
        del self._ff_context

    context = property(_get_context, _set_context, _del_context)

    @property
    def nodes(self) -> List[str]:
        return self._ff_nodes

    @property
    def params(self) -> Dict[str, Any]:
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
            if not isinstance(value, Compose):
                value = self._make_composable(value)

        return super().__setattr__(name, value)

    def _initialize(self):
        if self._ff_context is None:
            self._ff_context = init_object(settings.CONTEXT, safe=False)

        if not hasattr(self, "_ff_init_called"):
            raise RuntimeError(
                "Please call super().__init__(**params) in your __init__ method"
            )

        self._ff_initializing = True
        self._initialize_nodes()
        self._ff_initializing = False

    @classmethod
    def _collect_registered_params_and_nodes(cls) -> Tuple[List[str], List[str]]:
        """Return the list of all params and nodes registered in the Compose

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
    def _protected_keywords(cls) -> Dict[str, type]:
        """Return the protected keywords and the class that defines each of them"""
        keywords = {}
        for each_cls in cls.mro():
            for keyword in getattr(each_cls, "__dict__", {}).get("_keywords", []):
                if keyword in keywords:
                    continue
                keywords[keyword] = each_cls
        return keywords

    def _make_composable(self, value) -> "Compose":
        return ComposeProxy(ff_original_obj=value)

    def _prepare_child(self, child: "Compose", name: str):
        if self._ff_in_run:
            child._ff_prefix = f"{self._ff_prefix}.{self._ff_name}"
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

        for each_cls in cls.mro():
            for attr, attr_value in each_cls.__dict__.items():
                if isinstance(attr_value, Node) and attr not in nodes:
                    value = attr_value.__persist_flow__()
                    if isinstance(attr_value._default, type) and issubclass(
                        attr_value._default, Compose
                    ):
                        value["default"] = attr_value._default.describe()  # type:ignore
                    nodes[attr] = value
                elif isinstance(attr_value, Param) and attr not in params:
                    params[attr] = attr_value.__persist_flow__()

        return {
            "type": f"{cls.__module__}.{cls.__qualname__}",
            "params": params,
            "nodes": nodes,
        }

    def dump(self, ignore_depends: bool = True) -> dict:
        """Export the flow to a dictionary

        Args:
            ignore_depends: whether to ignore params and nodes that depend on others
        """
        nodes: dict = {}
        for node in self._ff_nodes:
            try:
                node_obj: Compose = getattr(self, node)
                if self.specs(node).get("depends_on", []) and ignore_depends:
                    continue
                nodes[node] = node_obj.dump(ignore_depends=ignore_depends)
            except Exception:
                nodes[node] = None

        params = {}
        for name, value in self.params.items():
            if self.specs(name).get("depends_on", []) and ignore_depends:
                continue
            try:
                params[name] = serialize(value)
            except ValueError as e:
                logger.warn(e)
                continue

        return {
            "type": f"{self.__module__}.{self.__class__.__qualname__}",
            "params": params,
            "nodes": nodes,
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

        definition = self.__class__.__dict__[path]
        if not isinstance(definition, (Param, Node)):
            raise ValueError(f"{path} is not a param or a node")

        return definition.to_dict()

    def missing(self) -> Dict[str, List[str]]:
        """Return the list of missing params and nodes"""
        params, nodes = [], []
        for attr in self._ff_params:
            if self.__class__.__dict__[attr]._depends_on:
                continue
            try:
                getattr(self, attr)
            except Exception:
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
            except Exception:
                nodes.append(attr)

        return {"params": params, "nodes": nodes}

    def get_from_path(self, path) -> Any:
        """Get a node or param by path

        Args:
            path: the path to the node or param (.) delimited

        Returns:
            Node or param, depending on the path
        """
        path = path.strip(".")

        if "." in path:
            module, subpath = path.split(".", 1)
            return getattr(self, module).get_from_path(subpath)

        return getattr(self, path)

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
        if isinstance(obj, Compose):
            func = obj.run
        elif isinstance(obj, type) and issubclass(obj, Compose):
            func = obj.run

        if specs["type"] == "param":
            return isinstance(obj, specs["type"])
        elif specs["type"] == "node":
            reference_input = specs["input"]
            reference_output = specs["output"]
            target_input = input_signature(func)
            target_output = output_signature(func)

            ok_input, ok_output = False, False
            if reference_input == empty:
                ok_input = True
            else:
                for name, annot in reference_input.items():
                    if name not in target_input:
                        ok_input = False
                        break
                    ok_input = is_compatible_with(target_input[name], annot)
                    if not ok_input:
                        break

            if reference_output == empty:
                ok_output = True
            else:
                ok_output = is_compatible_with(target_output, reference_output)
            return ok_input and ok_output

        raise ValueError(f"{path} is not a param or a node")

    def log_progress(self, name: Optional[str] = None, **kwargs):
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


class ComposeProxy(Compose):
    """Wrap an object to be a step.

    `ComposeProxy` demonstrates the same behavior as `Step`. The only difference is
    that `ComposeProxy` doesn't know how the object will be called (e.g. `__call__`
    or any methods) so it lazily exposes the methods when called.

    Cannot use this class directly because Compose reserves some common _keywords
    that can conflict with original object.

    Raise ValueError in case of conflict.
    """

    ff_original_obj: Callable

    def __init__(self, **params):
        super().__init__(**params)
        if isinstance(self.ff_original_obj, ComposeProxy):
            raise ValueError(
                "Unnecessary to wrap a ComposeProxy object with ComposeProxy"
            )

    def _create_callable(self, callable_obj):
        def wrapper(*args, **kwargs):
            # TODO: after remove _ff_name from kwargs, we might be able to remove this
            # wrapper
            return callable_obj(*args, **kwargs)

        if middlware_cfg := getattr(self, "Middleware"):
            next_call = wrapper
            for cls_name in reversed(middlware_cfg.middleware):
                cls = import_dotted_string(cls_name, safe=False)
                next_call = cls(obj=self, next_call=next_call)
            return next_call

        return wrapper

    def run(self, *args, **kwargs):
        """Pass-through to the original object"""
        return self.ff_original_obj.run(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        if self._ff_context is None:
            self._ff_context = init_object(settings.CONTEXT, safe=False)

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

        if self._ff_context is None:
            self._ff_context = init_object(settings.CONTEXT, safe=False)

        attr = getattr(self.ff_original_obj, name)
        if callable(attr):
            attr = self._create_callable(attr)
        return attr
