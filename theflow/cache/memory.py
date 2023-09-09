import logging
import multiprocessing
import multiprocessing.managers
import multiprocessing.synchronize
from typing import Any, Dict, Optional, Union

from .base import BaseCache

logger = logging.getLogger(__name__)
MANAGERS: Dict[str, multiprocessing.managers.SyncManager] = {}
LOCKS: Dict[str, multiprocessing.synchronize.RLock] = {}


class MemoryCache(BaseCache):
    """A memory-based cache

    This cache is quick to spin up and will terminate at the end of the process. It is
    suitable for testing and do small runs. It makes use of multiprocessing module to
    allow multiple processes to share the same cache.

    Args:
        uid: a unique identifier for the cache. If not provided, a fixed value "" will
            be used.
    """

    def __init__(self, uid: str = ""):
        """Initialize the object"""
        self.uid = uid
        if uid not in MANAGERS:
            MANAGERS[uid] = multiprocessing.Manager()

        if uid not in LOCKS:
            LOCKS[uid] = multiprocessing.RLock()

        self._msg_store: Union[dict, multiprocessing.managers.DictProxy] = MANAGERS[
            uid
        ].dict()

    def add(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        logger.info(f"Add: Timeout value ({timeout}) is ignored for memory cache")
        with LOCKS[self.uid]:
            if key not in self._msg_store:
                self._msg_store[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        with LOCKS[self.uid]:
            return self._msg_store.get(key, default)

    def delete(self, key: str) -> None:
        with LOCKS[self.uid]:
            if key in self._msg_store:
                del self._msg_store[key]

    def set(self, key: str, value: Any, timeout: Optional[int] = None) -> None:
        logger.info(f"Set: Timeout value ({timeout}) is ignored for memory cache")
        with LOCKS[self.uid]:
            self._msg_store[key] = value

    def touch(self, key: str, timeout: Optional[int] = None) -> None:
        logger.info(
            f"Touch ({key}): Timeout value ({timeout}) is ignored for memory cache"
        )

    def clear(self) -> None:
        with LOCKS[self.uid]:
            self._msg_store.clear()

    def close(self) -> None:
        self._msg_store = self._msg_store.copy()
        if self.uid in MANAGERS:
            MANAGERS[self.uid].shutdown()
            del MANAGERS[self.uid]
        if self.uid in LOCKS:
            del LOCKS[self.uid]

    def incr(self, key: str, delta: int = 1) -> int:
        with LOCKS[self.uid]:
            if key not in self._msg_store:
                self._msg_store[key] = 0
            self._msg_store[key] += delta
            return self._msg_store[key]

    def decr(self, key: str, delta: int = 1) -> int:
        return self.incr(key, -delta)

    def __contains__(self, key: str) -> bool:
        with LOCKS[self.uid]:
            return key in self._msg_store

    def __getitem__(self, key: str) -> Any:
        with LOCKS[self.uid]:
            return self._msg_store[key]

    def __setitem__(self, key: str, value: Any) -> None:
        with LOCKS[self.uid]:
            self._msg_store[key] = value

    def __delitem__(self, key: str) -> None:
        with LOCKS[self.uid]:
            del self._msg_store[key]

    @property
    def lock(self):
        return LOCKS[self.uid]
