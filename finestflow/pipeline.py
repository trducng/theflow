from pathlib import Path
from typing import Any, Optional, Union, Callable

from .config import Config, ConfigProperty
from .context import SimpleMemoryContext, BaseContext
from .step import StepWrapper
from .utils import is_parent_of_child
from .runs.base import RunTracker


RESERVED_PIPELINE_KEYWORDS = ["Config", "config", "initialize", "run", "last_run"]
RUN_EXTRA_PARAMS = ["_ff_from", "_ff_to"]


class Pipeline:
    """Subclass `Pipeline` to define and run your own flow

    Args:
        kwargs: the kwargs to pass to the flow and stored as `self._ff_kwargs`
            attribute
        config: the flow config can be either dictionary or a path to json/yaml file
        context: the context object for flow components to communicate with each other
    """

    _ff_init_called = False
    _ff_initializing = False
    config = ConfigProperty()

    def __init__(
        self,
        *,
        kwargs: Optional[dict] = None,
        config: Optional[Union[dict, str]] = None,
        context: Optional[BaseContext] = None,
    ):
        self._ff_init_called = True
        self._ff_kwargs = kwargs
        self._ff_config: Config = Config(config=config, cls=self.__class__)
        self._ff_context: BaseContext = (
            SimpleMemoryContext() if context is None else context
        )
        self.last_run: RunTracker = RunTracker(self._ff_context)
        self._ff_run_id: Optional[str] = None  # only available for root pipeline
        self._ff_nodes = []
        self._ff_initialize()
        self._ff_prefix: Optional[str] = None
        self._is_pipeline_nested: bool = False

    def initialize(self):
        raise NotImplementedError("Please declare your steps in `initialize`")

    def run(self, *args, **kwargs):
        raise NotImplementedError("Please route your steps into flow in `run`")

    def __setattr__(self, name: str, value: Any) -> None:
        if name == "_ff_init_called" or name == "_ff_initializing":
            return super().__setattr__(name, value)

        if not self._ff_init_called:
            raise AttributeError(
                "Please call `super().__init__()` at the top of your `__init__` method"
            )

        # wrap object into step
        if self._ff_initializing:
            if name in RESERVED_PIPELINE_KEYWORDS:
                raise AttributeError(
                    f"`{name}` is a reserved keyword. Please use different name"
                )

            if name.startswith("_ff"):
                raise AttributeError(f"Please don't start step name with `_ff`: {name}")

            if name in self._ff_nodes:
                raise AttributeError(
                    f"Step name `{name}` is duplicated. Please use different name"
                )

            self._ff_nodes.append(name)
            if isinstance(value, Pipeline):
                # TODO: should have a clone functionality
                value = value.__class__(
                    kwargs=value._ff_kwargs,
                    config=value._ff_config,
                    context=self._ff_context,
                )
                value.is_pipeline_nested(True)
            elif isinstance(value, StepWrapper):
                value = StepWrapper(
                    value._obj,
                    config=self._ff_config,
                    context=self._ff_context,
                )
            else:
                value = StepWrapper(
                    value,
                    config=self._ff_config,
                    context=self._ff_context,
                )

        return super().__setattr__(name, value)

    def _ff_initialize(self):
        self._ff_initializing = True
        self.initialize()
        self._ff_initializing = False

    def __call__(self, *args, **kwargs) -> Any:
        """Run the flow, accepting extra parameters for routing purpose"""
        _ff_name = self._handle_step_name(kwargs.pop("_ff_name", ""))
        if not self.is_pipeline_nested():
            # administrative setup
            self._ff_run_id = self.config.run_id
            self._ff_context.clear_all()
            self._ff_context.set("run_id", self._ff_run_id, context=None)
            self.last_run.config = self._ff_config.export()

        args, kwargs = self._handle_run_kwargs(*args, **kwargs)
        self._ff_context.create_local_context(context=_ff_name, exist_ok=True)

        if _from := self._ff_context.get("from"):
            if is_parent_of_child(_ff_name, _from):
                self._ff_context.set("good_to_run", False, context=_ff_name)

        output_ = self.run(*args, **kwargs)
        self.last_run.log_progress(
            _ff_name,
            input= {"args": args, "kwargs": kwargs},
            output= output_,
            status= "run"
        )

        # prepare the run path
        if not self.is_pipeline_nested():
            store_result: Optional[Path] = self.config.store_result
            if store_result is not None:
                self.last_run.persist(store_result, self._ff_run_id)

        return output_

    def _handle_step_name(self, _ff_name: str = "") -> str:
        """Combine the prefix and the step name, and pass it to the child steps.

        Args:
            _ff_name: the step name passed in from __call__ argument

        Returns:
            the processed step name
        """
        if self._ff_prefix is not None:
            if not _ff_name:
                raise AttributeError("Must provide _ff_name")
            if "." in _ff_name:
                raise AttributeError("_ff_name cannot contain `.`")
            if "*" in _ff_name:
                raise AttributeError("_ff_name cannot contain `*`")

            _ff_name = ".".join([self._ff_prefix, _ff_name])

        for node in self._ff_nodes:
            setattr(getattr(self, node), "_ff_prefix", _ff_name)

        return _ff_name

    def _handle_run_kwargs(self, *args, **kwargs) -> tuple[list, dict]:
        """Handle pipeline-specific kwargs passed into `run`.

        Args:
            args: the args passed into the pipeline
            kwargs: the kwargs passed into the pipeline

        Returns:
            a tuple of processed args and kwargs
        """
        if _ff_from := kwargs.pop("_ff_from", None):
            self._ff_context.set("from", _ff_from)
        if _ff_to := kwargs.pop("_ff_to", None):
            self._ff_context.set("to", _ff_to)
        if _ff_from_run := kwargs.pop("_ff_from_run", None):
            from_run = RunTracker(self._ff_context, "__from_run__")
            from_run.load(run_path=_ff_from_run)

        return args, kwargs

    def visualize(self):
        # 1 re-initialize the flow with different mode
        # 2 check the argument defintion passed into `run`
        # 3 run the flow with the fake argument
        # 4 track the graph

        raise NotImplementedError("Will implement visualize functionality later")

    def apply(self, fn: Callable):
        for node in self._ff_nodes:
            getattr(self, node).apply(fn)
        fn(self)
        return self

    def is_pipeline_nested(self, is_nested: Optional[bool] = None) -> bool:
        """Set whether the pipeline is nested or not

        Args:
            is_nested: set whether the pipeline is nested or not. If None, just return
                the current value

        Returns:
            whether the pipeline is nested or not
        """
        if is_nested is not None:
            self._is_pipeline_nested = is_nested

        return self._is_pipeline_nested
