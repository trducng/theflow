from pydantic import BaseModel


class Step(BaseModel):
    """
    Pydantic method:

    Pros:
        - allows to use type hint
        - do argument checking explicitly
        - allow recording argument specifically during object initialization, so that
        they can be recorded into the log, and can be reinitialized later

    Cons:
        - pydantic BaseModel requires use to declare internal attributes first in order
        to use them (e.g. _dummy)
        - seems unnecessary to use this in case you want to use it
        - the wrapper method is more entuitive to the users during usage
        - declaring and initializing isn't allow for flexible pipeline routing

    Verdict:
        - As allowing recording argument is very important, continue to use pydantic
        in the 1st place so that you can quickly gather other benefits out of it.
        - When the cons of pydantic interfere with the library usage, then reimplement
        the nice functionality of pydantic here. It's great to not have much dependency
        anyway.

    Wrapper method:

    Pros:
        - more intuitive for user, they do their own way and they don't need to care
        much about our tool

    Cons:
        - harder to initialize in a plug-n-play manner
            - don't guarantee
            - need Hydra-like configuration
        - harder to export config from the base params
        - the wrapper method doesn't work if the obj has __slots__ defined

    Note:
        - Provide flow.cond(<condition>) to control flow.
        - User can directly annotate in the code (either as inline comment that we can use
        through trace, or as params. Should be params, in case of for loop)
        - Automatic tracing can be affected by interacting with non-flow function
        (e.g. <obj>.is_true() within a function) -> Need type hinting for automated
        tracing to work. It should be doable, and the function should have good
        type-hint in order to do duck-typing.
            - Take a look at static code analyis tools:
                - coverage
                - https://github.com/scottrogowski/code2flow
                    - nice, but it doesn't work with method
                    - it doesn't show sequential graph
                - https://docs.python.org/3/library/ast.html
                    - quite nice for static analysis, can be used to trace the
                    graph
                    - https://stackoverflow.com/questions/30506381/getting-method-calls-and-their-arguments-from-method-object
                    - https://stackoverflow.com/questions/39719729/how-to-retrieve-a-control-flow-graph-for-python-code
                - https://github.com/ionelmc/python-hunter
                    - weird, cannot see how it show steps inside function
                - https://docs.python.org/3/library/trace.html
                    - requires running the trace, cannot do static analysis
                - https://github.com/ejrh/ejrh/blob/master/utils/pyan.py
                - https://stackoverflow.com/questions/8315389/how-do-i-print-functions-as-they-are-called
                - https://stackoverflow.com/questions/13963321/build-a-call-graph-in-python-including-modules-and-functions
                - https://stackoverflow.com/questions/50558849/python-how-to-trace-function-execution-order-in-large-project
            - Check type hint dynamically: https://typeguard.readthedocs.io/en/latest/
            - Create graph from AI

    Verdict: use static analysis to build the graph, don't need to do actual tracing
    """

    _dummy: bool = False
    _log: dict

    class Config:
        underscore_attrs_are_private = True

    # Don't explicitly call allows for step reusability
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._log = {
            "args": args,
            "kwargs": kwargs,
        }
        self.initialize()

    def run(self, *args, **kwargs):
        raise NotImplementedError("Please implement `run`")

    def initialize(self):
        pass


class Flow(Step):
    def build(self, config: dict):
        pass

    def export(self) -> dict:
        """Export flow to dict

        This can be used as config, for plug and play
        """
        pass


def go(*args, **kwargs):
    """Allow setting:

    - from: the name of the beginning task
    - to: the name of the last task
    - var: switching variable
    - config: override flow config
    - cache: the cache to use
    - name: experiment name
    """
    print("go")
    print(args)
    print(kwargs)


def list(*args, **kwargs):
    """List experiments"""
    print(args)
    print(kwargs)


def compare(*args, **kwargs):
    """Compare experiments"""
    print(args)
    print(kwargs)


def visualize(*args, **kwargs):
    """Visualize flow"""
    print(args)
    print(kwargs)


print("Need suggestion on how to organize pipeline experiments")


class Wrapper:
    def __init__(self, obj):
        self.__class__ = type(
            obj.__class__.__name__, (self.__class__, obj.__class__), {}
        )
        self.__dict__ = obj.__dict__
        import inspect

        skips = ["__init__"]
        for name, method in inspect.getmembers(obj, inspect.ismethod):
            if name in skips:
                continue

            def wrapper(*args, **kwargs):
                print(f"I know you call this function: {name}")
                return method(*args, **kwargs)

            setattr(self, name, wrapper.__get__(self, self.__class__))

    def __getattribute__(self, name):
        if name == "__class__" or name == "__dict__":
            return object.__getattribute__(self, name)

        attr = object.__getattribute__(self, name)
        if callable(attr):

            def wrapper(*args, **kwargs):
                print(f"I know you call this function: {name}")
                return attr(*args, **kwargs)

            wrapper.__func__.__name__ = name
            wrapper.__func__.__qualname__ = f"{self.__class__.__name__}.{name}"

            return wrapper

        return attr
