"""Define base pipeline functionalities that underly both pipeline and step"""
import inspect
import logging
from copy import deepcopy
from functools import lru_cache
from typing import (
    Any,
    Callable,
    Optional,
    _UnionGenericAlias,
    ForwardRef,
)

from .config import Config, ConfigProperty
from .context import BaseContext, SimpleMemoryContext
from .visualization import trace_pipelne_run


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


class Composable:
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
            "finestflow.middleware.TrackProgressMiddleware",
            "finestflow.middleware.SkipComponentMiddleware",
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

    def __init__(self, **params):
        self._ff_params: list[str] = []
        self._ff_nodes: list[str] = []
        self._ff_config: Optional[Config] = None
        self._ff_context: Optional[BaseContext] = None
        self._ff_prefix: Optional[str] = None  # only root node has prefix as None

        # collect
        self._ff_params, self._ff_nodes = self._collect_registered_params_and_nodes()

        self._ff_init_called = False
        for name, value in params.items():
            self.__setattr__(name, value)
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

        _ff_name = self._handle_step_name(kwargs.get("_ff_name", ""))
        if self._ff_prefix is None:  # only root node has prefix as None
            # administrative setup
            self._ff_run_id = self.config.run_id
            self.context.clear_all()
            self.context.set("run_id", self._ff_run_id, context=None)
            kwargs["_ff_name"] = _ff_name

        if _ff_name is not None:
            self.context.create_local_context(context=_ff_name, exist_ok=True)

        if self._middleware:
            return self._middleware(*args, **kwargs)
        return self._run(*args, **kwargs)

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
        return {key: self.__dict__[key] for key in self._ff_params}

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
        if self._ff_config is None:
            self._ff_config = Config(cls=self.__class__)
        if self._ff_context is None:
            self._ff_context = SimpleMemoryContext()

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
            for name, anno in getattr(each_cls, "__annotations__", {}).items():
                if name.startswith("_"):
                    logger.info(f"Skipping {name} as it starts with underscore")
                    continue

                if name in cls._protected_keywords():
                    raise ValueError(
                        f'"{name}" is a protected keyword, defined by "{cls._protected_keywords()[name]}"'
                    )

                if contains_composable_in_annotation(anno):
                    nodes.append(name)
                else:
                    params.append(name)

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

    def _info(self):
        nodes = {}
        for node in self._ff_nodes:
            if node in self.__dict__:
                nodes[node] = getattr(self, node)._info()
            else:
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

        if "ff_original_obj" not in self.__dict__:
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
