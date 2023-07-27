"""Define base pipeline functionalities that underly both pipeline and step"""
import inspect
import logging
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Optional, _UnionGenericAlias, ForwardRef

from .config import Config, ConfigProperty
from .context import BaseContext


logger = logging.getLogger(__name__)

class Composable:
    """Base class that handle basic logic of a composable component

    Everything is a composable component.

    This class:
        - Manages input parameters
        - Set up _ff_config and _ff_context
        - Defines base

    Initialization order:
        - initiate the parameters (by default inside __init__)
        - initiate the config and context
        - initiate the nodes
    """

    config = ConfigProperty()

    _keywords = [
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

    def initialize_nodes(self):
        pass

    def run(self, *args, **kwargs):
        pass

    def __call__(self, *args, **kwargs):
        if not hasattr(self, "_ff_initializing"):
            self._initialize()
        return self.run(*args, **kwargs)

    def __repr__(self):
        kwargs = ", ".join([f"{key}={repr(value)}" for key, value in self.params.items()])
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
            raise ValueError(f"Cannot set {self.__class__}.{name} to {value}: param {name} not declared")

    def _initialize(self):
        if not hasattr(self, "_ff_init_called"):
            raise RuntimeError(
                "Please call super().__init__(**params) in your __init__ method"
            )
        self._ff_initializing = True
        self.initialize_nodes()
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

        from .pipeline import Pipeline

        if isinstance(cls, _UnionGenericAlias):
            # Handle Union[...]
            for each_cls in cls.__args__:
                if isinstance(each_cls, ForwardRef):
                    try:
                        each_cls = each_cls._evaluate(globals(), locals(), frozenset())
                    except Exception:
                        logger.warning(f"Cannot evaluate ForwardRef {each_cls}. Assume not node")
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

    def _make_composable(self, node: Any) -> "Composable":
        return node
