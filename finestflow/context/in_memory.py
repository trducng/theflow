from typing import Any

from .base import BaseContext


class SimpleMemoryContext(BaseContext):
    """Simple context backed by in-memory dictionary

    The object is process-safe and can be used in multi-processing environment.
    """
    def __init__(self):
        self._msg_store = {}

    def set(self, name: str, value: Any) -> None:
        """Set a value to the context"""
        self._msg_store[name] = value

    def get(self, name, default=None):
        """Get a value from the context"""
        return self._msg_store.get(name, default)

    def make_process_safe(self) -> None:
        """Make the context process-safe"""
        import multiprocessing as mp

        self._msg_store = mp.Manager().dict(self._msg_store)