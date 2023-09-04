import logging
from typing import TYPE_CHECKING, Callable, Union

if TYPE_CHECKING:
    from .base import Compose, ComposeProxy

logger = logging.getLogger(__name__)


class Middleware:
    """Middleware template to work on the input and output of a node"""

    def __init__(self, obj: Union["Compose", "ComposeProxy"], next_call: Callable):
        from .base import Compose, ComposeProxy

        if obj is None:
            raise ValueError("obj must be specified")
        self.obj = obj
        self.obj_type: str = ""
        if isinstance(obj, ComposeProxy):
            self.obj_type = "step"
        elif isinstance(obj, Compose):
            self.obj_type = "pipeline"
        else:
            raise AttributeError(
                f"obj must be either Compose or ComposeProxy, got {type(obj)}"
            )
        self.next_call = next_call

    def run_step(self, *args, **kwargs):
        return args, kwargs

    def run_pipeline(self, *args, **kwargs):
        return args, kwargs

    def __call__(self, *args, **kwargs):
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

    def __call__(self, *args, **kwargs):
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
        from .runs.base import RunTracker

        # Gather the from, to and from_run from the root pipeline
        if _ff_from := kwargs.pop("_ff_from", None):
            self.obj.context.set("from", _ff_from, context=self.obj.flow_qualidx())
        if _ff_to := kwargs.pop("_ff_to", None):
            self.obj.context.set("to", _ff_to, context=self.obj.flow_qualidx())
        if _ff_from_run := kwargs.pop("_ff_from_run", None):
            from_run = RunTracker(self.obj, "__from_run__")
            from_run.load(run_path=_ff_from_run)

        self.obj.context.get("from", context=self.obj.flow_qualidx())
        if _from := self.obj.context.get("from", context=self.obj.flow_qualidx()):
            from .utils.paths import is_parent_of_child

            if is_parent_of_child(self.obj._ff_name, _from):
                self.obj.context.set("good_to_run", False, context=self.obj.qualidx())

        # Decide whether to run or fetch from the cache
        _ff_name = self.obj.abs_pathx()
        current_run = RunTracker(self.obj)

        good_to_run: bool = True
        if self.obj.context.has_context(context=self.obj.parent_qualidx()):
            good_to_run = self.obj.context.get(
                "good_to_run", default=True, context=self.obj.parent_qualidx()
            )

        if good_to_run is False:
            from .utils.paths import is_name_matched

            if is_name_matched(
                _ff_name, self.obj.context.get("from", context=self.obj.flow_qualidx())
            ):
                self.obj.context.set(
                    "good_to_run", True, context=self.obj.parent_qualidx()
                )
                logger.info(f"Run {_ff_name}. Turn good_to_run from False to True")
                current_run.log_progress(_ff_name, status="run")
                return self.next_call(*args, **kwargs)

            try:
                from_run = RunTracker(self.obj, which_progress="__from_run__")
                output = from_run.output(name=_ff_name)
                logger.info(f"Cached {_ff_name}")
                current_run.log_progress(_ff_name, status="cached")
                return output
            except Exception as e:
                logger.warning(f"Failed to get output from run: {e}")
                current_run.log_progress(_ff_name, status="run")
                return self.next_call(*args, **kwargs)

        if (
            self.obj.context.get("to", None, context=self.obj.flow_qualidx())
            == _ff_name
        ):
            self.obj.context.set("good_to_run", False, context=self.obj.flow_qualidx())

        current_run.log_progress(_ff_name, status="run")
        return self.next_call(*args, **kwargs)


class TrackProgressMiddleware(Middleware):
    """Store all information of the current run to the context

    A node can have 1 of the 3 states:
        - run: the node is run normally
        - cached: the node is not run, and the output is retrieved from the last run
    """

    def __call__(self, *args, **kwargs):
        from .runs.base import RunTracker

        self.obj.last_run = RunTracker(self.obj)

        if self.obj.abs_pathx() == ".":
            self.obj.last_run.config = (
                self.obj._ff_config.export()
            )  # pyright: reportOptionalMemberAccess=false

        _ff_name = self.obj.abs_pathx()
        _input = {"args": args, "kwargs": kwargs}
        _output = self.next_call(*args, **kwargs)
        self.obj.last_run.log_progress(_ff_name, input=_input, output=_output)

        if self.obj.abs_pathx() == ".":
            store_result = self.obj.config.store_result
            if store_result is not None and self.obj._ff_run_id:
                self.obj.last_run.persist(str(store_result), self.obj._ff_run_id)

        return _output
