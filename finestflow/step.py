import logging


logger = logging.getLogger(__name__)


class StepWrapper:
    """Transform existing object to follow step interface"""

    def __init__(self, obj, config, context):
        self._ff_obj = obj
        self._ff_config = config
        self._ff_prefix = ""
        # TODO: the context should be passed to the function
        self._ff_context = context

    def __getattr__(self, name):
        if name.startswith("_ff"):
            return super().__getattr__(name)

        attr = getattr(self._ff_obj, name)
        if callable(attr):

            def wrapper(*args, **kwargs):
                """Wrap the calls

                TODO: implement middleware-like approach to this wrapper.
                Don't let the wrapper definition here. It's too long and too hard 
                to debug.

                Possible performs:
                    - logging
                    - profiling
                    - caching
                    - retrying
                    - error handling
                """
                _ff_name: str = kwargs.pop("_ff_name", None)
                if not _ff_name or not isinstance(_ff_name, str):
                    # TODO: check for duplicated step name -> raise Error
                    # TODO: check for empty string -> raise Error
                    # TODO: check for non-string -> raise Error
                    # TODO: check for None -> raise Error
                    raise AttributeError(
                        "Should pass _ff_name when running the step to ensure reproducibility"
                    )
                _ff_name = f"{self._ff_prefix}.{_ff_name}"

                _status = "start"
                # if self._ff_config.get("mode") == 'trace':
                #     return "haha"
                if self._ff_context.get_context("good_to_run", default=True) is False:
                    import json

                    with open(self._ff_context.get_context("cache"), "r") as f:
                        # TODO: should have a dedicated libary to handle reading from cache
                        _input = {"args": args, "kwargs": kwargs}
                        _temp = json.load(f)[_ff_name]
                        _status = "cached"
                        _output = _temp["output"]
                    if self._ff_context.get_context("from", None) == _ff_name:
                        _output = attr(*_input["args"], **_input["kwargs"])
                        _status = "rerun"
                        self._ff_context.add_context("good_to_run", True)

                    # TODO: should put "input" context earlier to save the input into cache in case of failure
                    self._ff_context.add_context(
                        _ff_name,
                        {"input": _input, "output": _output, "status": _status},
                    )
                    return _output

                if self._ff_context.get_context("to", None) == _ff_name:
                    self._ff_context.add_context("good_to_run", False)

                _input = {"args": args, "kwargs": kwargs}
                _output = attr(*args, **kwargs)
                _status = "run"
                self._ff_context.add_context(
                    _ff_name, {"input": _input, "output": _output, "status": _status}
                )
                return _output

            wrapper.__name__ = name
            wrapper.__qualname__ = f"{self._ff_obj.__class__.__name__}.{name}"

            return wrapper

        return attr

    def __setattr__(self, name, value):
        if name.startswith("_ff"):
            return super().__setattr__(name, value)

        return getattr(self._ff_obj, name).__setattr__(name, value)

    def __call__(self, *args, **kwargs):
        return self.__getattr__("__call__")(*args, **kwargs)

    def __add__(self, other):
        return self.__getattr__("__add__")(other)
