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

    def set(self, name: str, value: Any) -> None:
        """Set a value to the context"""
        if self._lock is not None:
            with self._lock:
                self._msg_store[name] = value
            return

        self._msg_store[name] = value

    def get(self, name: Optional[str], default=None):
        """Get a value from the context"""
        if name is None:
            if self._lock is None:
                return self._msg_store
            return self._msg_store.copy()
    
        return self._msg_store.get(name, default)

    def clear(self, name):
        """Clear a value from the context"""
        if self._lock is not None:
            with self._lock:
                if name in self._msg_store:
                    del self._msg_store[name]
            return

        if name in self._msg_store:
            del self._msg_store[name]

    def activate_multiprocessing(self) -> None:
        """Make the context process-safe"""
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
