import logging
from typing import Callable, Union, TYPE_CHECKING
from .base import Composable

if TYPE_CHECKING:
    from .pipeline import Pipeline
    from .step import Step, StepProxy

logger = logging.getLogger(__name__)


class Middleware(Composable):
    """Middleware template to work on the input and output of a node"""

    next_call: Union[Composable, Callable]
    obj: Union["Pipeline", "Step", "StepProxy"]

    _keywords = ["obj_type"]

    def __init__(self, **params):
        super().__init__(**params)

        from .pipeline import Pipeline
        from .step import Step, StepProxy

        obj = params.get("obj", None)
        if obj is None:
            raise ValueError("obj must be specified")
        self.obj_type: str = ""
        if isinstance(obj, Pipeline):
            self.obj_type = "pipeline"
        elif isinstance(obj, (Step, StepProxy)):
            self.obj_type = "step"
        else:
            raise AttributeError(
                f"obj must be either Pipeline or Step, got {type(obj)}"
            )

    def run_step(self, *args, **kwargs):
        return args, kwargs

    def run_pipeline(self, *args, **kwargs):
        return args, kwargs

    def run(self, *args, **kwargs):
        if self.obj_type == "step":
            return self.run_step(*args, **kwargs)
        elif self.obj_type == "pipeline":
            return self.run_pipeline(*args, **kwargs)
        raise NotImplementedError(f"Haven't implemented for {self.obj_type}")


class SkipComponentMiddleware(Middleware):
    """Skip executing the component if the user specifies so

    This middleware utilizes the following context key:
        - good_to_run: if True, the component can be run
        - from: skip components in a pipeline earlier than the specified component
        - to: skip components in a pipeline later than the specified component (only
            valid for parallel)

    This middleware utilizes the following context name:
        - __from_run__: this context store the output of the previous run, specified
        by the user

    This middleware reserves these kwargs when calling run:
        - _ff_from_run: the path to the past run tracker, which will be used to
        substitute output of skipped steps
        - _ff_from: skip the steps earlier than the specified step
        - _ff_to: skip the steps later than the specified step (only valid for parallel)

    """

    def run_step(self, *args, **kwargs):
        """Run the middleware in the context of a wrapping step

        If the step is marked as good_to_run. Run the step as usual.
        If the step is not marked as good_to_run:
            - Check if the step name matches the name from `from`. If so, it means that
            we would want to run this step (as probably all the steps before this step
            in the pipeline have been skipped). So we will run this step, and mark
            good_to_run as True so that later step will be run as normal.
            - Check if the step name matchs the name from `to`. If so, we will run this
            step and mark good_to_run as False so that later step will be skipped.
        """
        _ff_name = kwargs.get("_ff_name", None)
        if _ff_name is None:
            return self.next_call(*args, **kwargs)
        _ff_name = f"{self.obj._ff_prefix}.{_ff_name}"

        if (
            self.obj.context.get(
                "good_to_run", default=True, context=self.obj._ff_prefix
            )
            is False
        ):
            from .utils import is_name_matched

            if is_name_matched(_ff_name, self.obj.context.get("from", context=None)):
                self.obj.context.set("good_to_run", True, context=self.obj._ff_prefix)
                logger.info(f"Run {_ff_name}. Turn good_to_run from False to True")
                return self.next_call(*args, **kwargs)

            from .runs.base import RunTracker

            try:
                from_run = RunTracker(self.obj.context, which_progress="__from_run__")
                output = from_run.output(name=_ff_name)
                logger.info(f"Cached {_ff_name}")
                return output
            except Exception as e:
                logger.warning(f"Failed to get output from run: {e}")
                return self.next_call(*args, **kwargs)

        if self.obj.context.get("to", None) == _ff_name:
            self.obj.context.set("good_to_run", False, context=self.obj._ff_prefix)

        return self.next_call(*args, **kwargs)

    def run_pipeline(self, *args, **kwargs):
        """Run the middleware in the context of wrapping the pipeline"""
        # Gather the from, to and from_run from the root pipeline
        if _ff_from := kwargs.pop("_ff_from", None):
            self.obj.context.set("from", _ff_from)
        if _ff_to := kwargs.pop("_ff_to", None):
            self.obj.context.set("to", _ff_to)
        if _ff_from_run := kwargs.pop("_ff_from_run", None):
            from .runs.base import RunTracker

            from_run = RunTracker(self.obj.context, "__from_run__")
            from_run.load(run_path=_ff_from_run)

        _ff_name = kwargs.get("_ff_name", None)
        if _ff_name is None:
            return self.next_call(*args, **kwargs)

        if _from := self.obj.context.get("from"):
            from .utils import is_parent_of_child

            if is_parent_of_child(_ff_name, _from):
                self.obj.context.set("good_to_run", False, context=_ff_name)

        return self.next_call(*args, **kwargs)


class TrackProgressMiddleware(Middleware):
    """Store all information of the current run to the context

    Note: this assumes that the input and output of the wrapped function are pickleable.
    """

    def run_step(self, *args, **kwargs):
        _ff_name = kwargs.get("_ff_name", None)
        if _ff_name is None:
            return self.next_call(*args, **kwargs)

        _ff_name = (
            _ff_name
            if self.obj._ff_prefix is None
            else f"{self.obj._ff_prefix}.{_ff_name}"
        )

        _input = {"args": args, "kwargs": kwargs}
        _output = self.next_call(*args, **kwargs)
        self.obj.last_run.log_progress(_ff_name, input=_input, output=_output)

        return _output

    def run_pipeline(self, *args, **kwargs):
        if not self.obj._is_pipeline_nested:  # pyright: reportGeneralTypeIssues=false
            self.obj.last_run.config = (
                self.obj._ff_config.export()
            )  # pyright: reportOptionalMemberAccess=false

        output = self.run_step(*args, **kwargs)
        if not self.obj._is_pipeline_nested:
            store_result = self.obj.config.store_result
            if store_result is not None and isinstance(self.obj._ff_run_id, str):
                self.obj.last_run.persist(str(store_result), self.obj._ff_run_id)

        return output

    def run(self, *args, **kwargs):
        from .runs.base import RunTracker

        self.obj.last_run = RunTracker(self.obj.context)
        return super().run(*args, **kwargs)
