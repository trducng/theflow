"""Context manager for each run

The context for each run has the following format:
- private: each step has its own private context
- shared: all steps can access information in this shared context
"""
from typing import Callable, Optional


class Context(object):
    pass


class InMemoryDictionary(Context):
    def __init__(self):
        self._shared = {}

    def add_context(self, name, value):
        self._shared[name] = value

    def get_context(self, name, default=None):
        return self._shared.get(name, default)

    def sub_context(self, name) -> Callable:
        sub_context = InMemoryDictionary(shared_context=self._shared)
        # TODO: should provide a handler like rpc callback for step to access the context
        # it will access the same context, and it will be less complicated to manage
        self._private[name] = sub_context

        return sub_context

    def to_dict(self) -> dict:
        # TODO: handle to_dict recursively
        # TODO: should also have a persist function
        return self._shared