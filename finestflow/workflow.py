import time
import uuid
from pathlib import Path
from typing import Any, Optional, Union, Callable

from .context import SimpleMemoryContext, BaseContext
from .step import StepWrapper

RESERVED_PIPELINE_KEYWORDS = ["Config"]
RUN_EXTRA_PARAMS = ["_ff_from", "_ff_to"]


class YourFlow:
    """Subclass `YourFlow` to define and run your own flow

    Args:
        kwargs: the kwargs to pass to the flow and stored as `self._ff_kwargs`
            attribute
        config: the flow config can be either dictionary or a path to json/yaml file
        context: the context object for flow components to communicate with each other
    """

    _ff_init_called = False
    _ff_initializing = False

    class _FF_Callbacks:
        run_name: Callable = lambda obj: time.time()
        log_dir: Callable = lambda obj: Path("logs") / obj._run

    class _FF_Config:
        default_config = {}

    def __init__(
        self,
        *,
        kwargs: Optional[dict] = None,
        config: Optional[Union[dict, str]] = None,
        context: Optional[BaseContext] = None,
    ):
        self._ff_init_called = True
        self._ff_kwargs = kwargs
        if config is None:
            config = {}
        if isinstance(config, str):
            import json

            with open(config, "r") as f:
                config = json.load(f)
        self._ff_config: dict = config
        self._ff_run_context: BaseContext = (
            SimpleMemoryContext() if context is None else context
        )
        self._ff_nodes = []
        self._run = str(int(time.time()))
        self._ff_initialize()
        self._ff_prefix: Optional[str] = None
        self._ff_callbacks: dict = []

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
                raise AttributeError(
                    f"Please don't start step name with `_ff`: {name}"
                )

            if name in self._ff_nodes:
                raise AttributeError(
                    f"Step name `{name}` is duplicated. Please use different name"
                )

            self._ff_nodes.append(name)
            if isinstance(value, YourFlow):
                # TODO: should have a clone functionality
                value = value.__class__(
                    kwargs=value._ff_kwargs,
                    config=value._ff_config,
                    context=self._ff_run_context
                )
            elif isinstance(value, StepWrapper):
                value = StepWrapper(
                    value._obj,
                    config=self._ff_config,
                    context=self._ff_run_context,
                )
            else:
                value = StepWrapper(
                    value,
                    config=self._ff_config,
                    context=self._ff_run_context,
                )

        return super().__setattr__(name, value)

    def _ff_initialize(self):
        self._ff_initializing = True
        self.initialize()
        self._ff_initializing = False

    def __call__(self, *args, **kwargs) -> Any:
        """Run the flow, accepting extra parameters for routing purpose"""
        # TODO: these configs are too hectic, should have better abstraction
        _ff_from: str = kwargs.pop("_ff_from", None)
        _ff_to: str = kwargs.pop("_ff_to", None)
        _ff_from_cache: str = kwargs.pop("_ff_from_cache", None)
        _ff_cache_dir: str = kwargs.pop("_ff_cache_dir", None)
        if _ff_from:
            self._ff_run_context.set("from", _ff_from)
            self._ff_run_context.set("good_to_run", False)
        if _ff_to:
            self._ff_run_context.set("to", _ff_to)
        if _ff_from_cache:
            self._ff_run_context.set("cache", _ff_from_cache)
        if _ff_cache_dir:
            cache_dir = Path(_ff_cache_dir) / self._run
            self._ff_run_context.set("cache_dir", _ff_cache_dir)
        else:
            cache_dir = None
        # TODO: it should set more context about the name of the current edge here
        _ff_name = kwargs.pop("_ff_name", "")
        if self._ff_prefix is not None:
            if not _ff_name:
                raise AttributeError("Must provide _ff_name")
            _ff_name = f"{self._ff_prefix}.{_ff_name}"
        for node in self._ff_nodes:
            setattr(getattr(self, node), "_ff_prefix", _ff_name)

        output_ = self.run(*args, **kwargs)
        self._ff_run_context.set(_ff_name, output_)
        if cache_dir is not None:
            Path(cache_dir).mkdir(parents=True, exist_ok=True)
            with (Path(cache_dir) / "cache.json").open("w") as fo:
                import json
                json.dump(self._ff_run_context.get(name=None), fo)
        return output_

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
