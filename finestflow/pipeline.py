from typing import Any, Optional, Callable

from .step import StepProxy
from .visualization import trace_pipelne_run
from .base import Composable

from finestflow.config import Config
from finestflow.context import SimpleMemoryContext


class Pipeline(Composable):
    """Subclass `Pipeline` to define and run your own flow

    Args:
        kwargs: the kwargs to pass to the flow and stored as `self._ff_kwargs`
            attribute
        config: the flow config can be either dictionary or a path to json/yaml file
        context: the context object for flow components to communicate with each other
    """

    _keywords = ["last_run", "apply", "Middleware", "middleware"]

    class Middleware:
        middleware = [
            "finestflow.middleware.TrackProgressMiddleware",
            "finestflow.middleware.SkipComponentMiddleware",
        ]

    def __init__(self, **params):
        super().__init__(**params)
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
        kwargs.pop("_ff_name", None)
        return self.run(*args, **kwargs)

    def _make_composable(self, value) -> Composable:
        if isinstance(value, Pipeline):
            value._is_pipeline_nested = True
        elif isinstance(value, StepProxy):
            pass
        else:
            value = StepProxy(ff_original_obj=value)

        return value

    def _initialize(self):
        if self._ff_config is None:
            self.config = Config(cls=self.__class__)
        if self._ff_context is None:
            self.context = SimpleMemoryContext()
        super()._initialize()
        for node in self.nodes:
            getattr(self, node).config = self._ff_config
            getattr(self, node).context = self._ff_context

    def __call__(self, *args, **kwargs) -> Any:
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
