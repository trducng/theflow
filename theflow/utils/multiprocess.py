import multiprocessing
import multiprocessing.managers
import threading
import uuid
from typing import TYPE_CHECKING, Dict, List, cast

if TYPE_CHECKING:
    from ..base import Compose

MANAGERS: Dict[str, multiprocessing.managers.BaseManager] = {}
LOCKS: Dict[str, threading.Lock] = {}


def _run_node(task):
    obj: "Compose" = task[0]
    child_name: str = task[1]
    uid: str = task[2]
    params: Dict = task[3]

    with LOCKS[uid]:
        node = getattr(obj, child_name)
    return node(**params)


def parallel(obj: "Compose", child_name: str, tasks: List[Dict], **kwargs):
    """Run a node in parallel with multiprocessing"""

    key = uuid.uuid4().hex
    manager = None
    try:
        manager = multiprocessing.Manager()
        obj._ff_childs_called = cast("dict", manager.dict(obj._ff_childs_called))
        lock = manager.Lock()
        MANAGERS[key] = manager
        LOCKS[key] = lock

        tasks_mp = [(obj, child_name, key, task) for task in tasks]
        with multiprocessing.Pool(**kwargs) as pool:
            yield from pool.imap(_run_node, tasks_mp)
    finally:
        if isinstance(obj._ff_childs_called, multiprocessing.managers.DictProxy):
            obj._ff_childs_called = obj._ff_childs_called.copy()
        if manager is not None:
            manager.shutdown()
        if key in MANAGERS:
            del MANAGERS[key]
        if key in LOCKS:
            del LOCKS[key]
