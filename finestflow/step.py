import logging
from typing import Callable

from .base import Composable
from .config import Config
from .context import SimpleMemoryContext


logger = logging.getLogger(__name__)



class StepProxy(Composable):
    """Wrap an object to be a step.

    `StepProxy` demonstrates the same behavior as `Step`. The only difference is that
    `StepProxy` doesn't know how the object will be called (e.g. `__call__` or any
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
        if isinstance(self.ff_original_obj, StepProxy):
            raise ValueError("Unnecessary to wrap a StepProxy object with StepProxy")

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
