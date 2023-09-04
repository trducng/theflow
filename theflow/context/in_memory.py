import multiprocessing
from typing import Any, Optional

from .base import BaseContext

_MANAGER = None


class SimpleMemoryContext(BaseContext):
    """Simple context backed by in-memory dictionary

    The object is process-safe and can be used in multi-processing environment.
    """

    def __init__(self):
        self._msg_store = {}
        self._lock = None  # if not None, then _msg_store is a DictProxy

        self._global_key = "__global_key__"
        self._msg_store[self._global_key] = {}

    def _is_context_valid(self, context: Optional[str]) -> str:
        """Check if the context name is valid

        Args:
            context: name of the context

        Returns:
            name of the context
        """
        if context is None:
            context = self._global_key

        if not isinstance(context, str):
            raise ValueError(
                f"Context name must be a string or None, got {type(context)}"
            )

        if context not in self._msg_store:
            raise ValueError(f"Context {context} does not exist")

        return context

    def set(self, name: str, value: Any, context: Optional[str] = None) -> None:
        context = self._is_context_valid(context)
        if self._lock is not None:
            with self._lock:
                current = self._msg_store[context]
                current[name] = value
                self._msg_store[context] = current
            return

        self._msg_store[context][name] = value

    def get(
        self, name: Optional[str], default=None, context: Optional[str] = None
    ) -> Any:
        context = self._is_context_valid(context)
        if name is None:
            if self._lock is None:
                return self._msg_store[context].copy()
            return self._msg_store[context].copy()

        return self._msg_store[context].get(name, default)

    def clear(self, name: Optional[str], context: Optional[str]):
        context = self._is_context_valid(context)
        if self._lock is not None:
            with self._lock:
                if name in self._msg_store:
                    del self._msg_store[context][name]
            return

        if name in self._msg_store:
            del self._msg_store[context][name]

    def clear_all(self):
        if self._lock is not None:
            with self._lock:
                for key in self._msg_store.keys():
                    self._msg_store[key].clear()
            return

        for key in self._msg_store.keys():
            self._msg_store[key].clear()
        self._msg_store[self._global_key] = {}

    def has_context(self, context: str) -> bool:
        return context in self._msg_store

    def create_context(self, context: str, exist_ok=False) -> str:
        if context == self._global_key:
            raise ValueError(f"Cannot use {context} as context name")

        if not isinstance(context, str):
            raise ValueError(f"Context name must be a string, got {type(context)}")

        if context in self._msg_store:
            if exist_ok:
                return context
            raise ValueError(f"Context {context} already exists")

        self._msg_store[context] = {}
        return context

    def activate_multiprocessing(self) -> None:
        """Make the context process-safe

        TODO: this is not a good way to do it, because multiple pipelines may have
        multiprocessing at the same time, and hence any pipeline finishes
        multiprocessing first will deactivate the multiprocessing for all other
        pipelines.

        1. One solution is to make this context multiprocessing-friendly by default. If
        going with this solution, we need to figure out a way to close the context when
        the main pipeline finishes. Maybe with a context manager, and then register
        callbacks, or with the `with` statement.
        2. Another solution is to make the activate/deactivate multiprocessing works
        based on the pipeline name. However, we still have the global context to deal
        with.

        Since multiprocessing is subject to platform-specific idiosyncracies, we should
        separate multiprocessing context from non-multiprocessing context. So that in
        very simple use cases, the flow run without any problem. This approach has one
        downside that it requires users to be aware and manually switching to the
        multiprocessing context when their pipeline has multiprocessing.

        Context manager can be used to make the context switching easier.

        The context is also should be separated by run. All the more reasons to have
        a context manager. Not so. We do not intend for the context manager to exists
        in a separate processes. Then we do not need it.
        """
        global _MANAGER

        _MANAGER = multiprocessing.Manager()
        self._msg_store = _MANAGER.dict(self._msg_store)
        self._lock = _MANAGER.Lock()

    def deactivate_multiprocessing(self) -> None:
        """Destroy the context in a multi-processing environment"""
        global _MANAGER

        if _MANAGER is not None:
            self._msg_store = self._msg_store.copy()
            _MANAGER.shutdown()
            _MANAGER = None
            self._lock = None
