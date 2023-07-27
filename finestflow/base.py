"""Define base pipeline functionalities that underly both pipeline and step"""
import inspect
import logging
from copy import deepcopy
from typing import (
    TYPE_CHECKING,
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
        "middleware",
        "Config",
        "config",
        "run",
        "params",
        "prefix",
        "nodes",
        "context",
        "initialize_nodes",
    ]

    def __init__(self, **params):
        self.params, self.nodes = {}, []
        self._ff_config: Optional[Config] = None
        self._ff_context: Optional[BaseContext] = None
        self._ff_prefix: Optional[str] = None

        self._ff_init_called = False
        keywords = self._protected_keywords()
        for name, value in params.items():
            if name.startswith("_"):
                raise ValueError(f"Parameter name cannot start with underscore: {name}")
            if name in keywords:
                raise ValueError(
                    f"Parameter name cannot be a protected keyword: {name}"
                )
            self.__setattr__(name, value)
        self._ff_init_called = True

        self._ff_run_id: Optional[str] = None  # only available for root pipeline
        self._is_pipeline_nested: bool = False
        self.middleware = None
        if middlware_cfg := getattr(self, "Middleware"):
            from .utils import import_dotted_string

            next_call = self._run
            for cls_name in reversed(middlware_cfg.middleware):
                cls = import_dotted_string(cls_name)
                next_call = cls(obj=self, next_call=next_call)
            self.middleware = next_call

    def _run(self, *args, **kwargs):
        """Subclass to handle pre- and post- run"""
        kwargs.pop("_ff_name", None)
        return self.run(*args, **kwargs)

    def initialize_nodes(self):
        pass

    def run(self, *args, **kwargs):  # type: ignore
        raise NotImplementedError(f"Please implement {self.__class__.__name__}.run")

    def __call__(self, *args, **kwargs):
        """Run the flow, accepting extra parameters for routing purpose"""
        if not hasattr(self, "_ff_initializing"):
            self._initialize()

        _ff_name = self._handle_step_name(kwargs.get("_ff_name", ""))
        if not self._is_pipeline_nested:
            # administrative setup
            self._ff_run_id = self.config.run_id
            self.context.clear_all()
            self.context.set("run_id", self._ff_run_id, context=None)
            kwargs["_ff_name"] = _ff_name

        if _ff_name is not None:
            self.context.create_local_context(context=_ff_name, exist_ok=True)

        if self.middleware:
            return self.middleware(*args, **kwargs)
        return self._run(*args, **kwargs)

    def __repr__(self):
        kwargs = ", ".join(
            [f"{key}={repr(value)}" for key, value in self.params.items()]
        )
        return f"{self.__class__.__name__}({kwargs})"

    def __str__(self):
        return f"{self.__class__.__name__} (nodes: {self.nodes})"

    def _get_context(self) -> BaseContext:
        if self._ff_context is None:
            raise ValueError("Context is not set")
        return self._ff_context

    def _set_context(self, context: BaseContext) -> None:
        self._ff_context = context
        for node in self.nodes:
            if isinstance(getattr(self, node), Composable):
                getattr(self, node).context = context

    def _del_context(self) -> None:
        del self._ff_context

    context = property(_get_context, _set_context, _del_context)

    def __setattr__(self, name: str, value: Any) -> None:
        if name.startswith("_"):
            return super().__setattr__(name, value)

        if self._is_node(name):
            if name.startswith("_"):
                raise ValueError(f"Node name cannot start with underscore: {name}")
            self.nodes.append(name)
            value = self._make_composable(value)
        elif self._is_param(name):
            self.params[name] = deepcopy(value)

        try:
            return super().__setattr__(name, value)
        except Exception:
            raise ValueError(
                f"Cannot set {self.__class__}.{name} to {value}: param {name} not declared"
            )

    def _initialize(self):
        if self._ff_config is None:
            self.config = Config(cls=self.__class__)
        if self._ff_context is None:
            self.context = SimpleMemoryContext()

        if not hasattr(self, "_ff_init_called"):
            raise RuntimeError(
                "Please call super().__init__(**params) in your __init__ method"
            )

        self._ff_initializing = True
        self.initialize_nodes()
        for node in self.nodes:
            getattr(self, node).config = self._ff_config
            getattr(self, node).context = self._ff_context
        self._ff_initializing = False

    def _declared_params(self) -> dict:
        """Return all parameters and their values"""
        params = {}
        for cls in self.__class__.mro():
            for name, _ in inspect.getmembers(cls):
                if name.startswith("_"):
                    continue
                if name in params:
                    continue
                obj = getattr(self, name)
                if inspect.ismethod(obj):
                    continue
                params[name] = obj

        for name in getattr(self, "__annotations__", {}).keys():
            if name in params:
                continue
            obj = getattr(self, name, None)
            if inspect.ismethod(obj):
                continue
            params[name] = obj

        return params

    def _protected_keywords(self) -> list[str]:
        """List out protected keywords, not meant to be used"""
        keywords = []
        for cls in self.__class__.mro():
            keywords += getattr(cls, "_keywords", [])
        return list(sorted(set(keywords)))

    def _is_node(self, name: str) -> bool:
        if getattr(self, "_ff_initializing", False):
            # During node initialization
            return True

        # In __init__, separate from params to nodes
        cls = getattr(self, "__annotations__", {}).get(name)
        if cls is None:
            return False

        if isinstance(cls, _UnionGenericAlias):
            # Handle Union[...]
            for each_cls in cls.__args__:
                if isinstance(each_cls, ForwardRef):
                    try:
                        each_cls = each_cls._evaluate(globals(), locals(), frozenset())
                    except Exception:
                        logger.warning(
                            f"Cannot evaluate ForwardRef {each_cls}. Assume not node"
                        )
                        continue

                # TODO: nested type
                if inspect.isclass(each_cls) and issubclass(each_cls, Composable):
                    return True

            return False

        if isinstance(cls, ForwardRef):
            try:
                cls = cls._evaluate(globals(), locals(), frozenset())
            except Exception:
                logger.warning(f"Cannot evaluate ForwardRef {cls}. Assume not node.")
                return False

        if inspect.isclass(cls):
            return issubclass(cls, Composable)

        return False

    def _is_param(self, name: str) -> bool:
        if self._is_node(name):
            return True

        if getattr(self, "_ff_init_called", None) is False:
            # During base __init__
            return True

        return False

    def _make_composable(self, value) -> "Composable":
        if isinstance(value, Composable):
            value._is_pipeline_nested = True
        elif isinstance(value, ComposableProxy):
            pass
        else:
            value = ComposableProxy(ff_original_obj=value)

        return value

    def _handle_step_name(self, _ff_name: str = "") -> str:
        """Combine the prefix and the step name, and pass it to the child steps.

        Args:
            _ff_name: the step name passed in from __call__ argument

        Returns:
            the processed step name
        """
        if self._ff_prefix is not None:
            if "." in _ff_name:
                raise AttributeError("_ff_name cannot contain `.`")
            if "*" in _ff_name:
                raise AttributeError("_ff_name cannot contain `*`")

            _ff_name = ".".join([self._ff_prefix, _ff_name])

        for node in self.nodes:
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
        for node in self.nodes:
            getattr(self, node).apply(fn)
        fn(self)
        return self


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

    _keywords = ["last_run", "Middleware", "middlewares"]

    class Middleware:
        middleware = [
            "finestflow.middleware.TrackProgressMiddleware",
            "finestflow.middleware.SkipComponentMiddleware",
        ]

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

    def initialize_nodes(self, *args, **kwargs):
        """Pass-through to the original object"""
        return self.ff_original_obj.initialize_nodes(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        if self._ff_config is None:
            self.config = Config(cls=self.__class__)
        if self._ff_context is None:
            self.context = SimpleMemoryContext()

        return self._create_callable(getattr(self.ff_original_obj, "__call__"))(
            *args, **kwargs
        )

    def __getattr__(self, name):
        if name.startswith("_"):
            return super().__getattr__(name)

        if "ff_original_obj" not in self.__dict__:
            raise AttributeError(
                f"{self.__class__.__name__} object has no attribute {name}"
            )

        if self._ff_config is None:
            self.config = Config(cls=self.__class__)
        if self._ff_context is None:
            self.context = SimpleMemoryContext()

        attr = getattr(self.ff_original_obj, name)
        if callable(attr):
            attr = self._create_callable(attr)
        return attr
