"""Construct a flow declaratively in a safe manner."""
import logging
from typing import Dict, Optional, Type

from .base import Compose
from .utils.modules import deserialize, import_dotted_string

logger = logging.getLogger(__name__)
NATIVE_TYPE = (dict, list, tuple, str, int, float, bool, type(None))


def load(
    obj: dict,
    /,
    safe=True,
    allowed_modules: Optional[Dict[str, Type]] = None,
) -> Compose:
    """Construct flow from exported dict

    Args:
        obj: flow configuration exported with Flow.dump()
        safe: if True, only allowed modules can be imported
        modules: dict of allowed modules

    Returns:
        Compose: flow
    """
    cls: Type["Compose"]
    if safe:
        if allowed_modules is None:
            raise ValueError("A dict of allowed modules not provided when safe=True")
        if obj["type"] not in allowed_modules:
            raise ValueError(
                f"Module {obj['type']} not allowed. "
                f"Allowed modules are {list(allowed_modules.keys())}"
            )
        cls = allowed_modules[obj["type"]]
    else:
        cls = import_dotted_string(
            obj["type"], safe=safe, allowed_modules=allowed_modules
        )

    params: dict = {}
    for name, value in obj["params"].items():
        try:
            params[name] = deserialize(
                value, safe=safe, allowed_modules=allowed_modules
            )
        except Exception as e:
            logger.warn(e)
            continue

    nodes: dict = {
        key: load(value, safe=safe, allowed_modules=allowed_modules)
        for key, value in obj["nodes"].items()
    }

    return cls(**params, **nodes)


def create(
    obj: dict,
    /,
    safe=True,
    allowed_modules: Optional[Dict[str, Type]] = None,
) -> Optional[Type[Compose]]:
    pass
