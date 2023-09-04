import importlib
import inspect
import logging
from typing import Any, Dict, Optional, Type

logger = logging.getLogger(__name__)
NATIVE_TYPE = (dict, list, tuple, str, int, float, bool, type(None))


def import_dotted_string(
    dotted_string: str, /, safe=True, allowed_modules: Optional[Dict[str, Type]] = None
):
    """Import a dotted string

    Args:
        dotted_string: the dotted string to import
        safe: if True, only allowed modules can be imported
        allowed_modules: dict of allowed modules

    Returns:
        the imported object
    """
    if safe:
        if allowed_modules is None:
            raise ValueError("Must provide allowed_modules when safe=True")

        if dotted_string not in allowed_modules:
            raise ValueError(
                f"Module {dotted_string} is not allowed. "
                f"Allowed modules are {list(allowed_modules.keys())}"
            )

        return allowed_modules[dotted_string]

    # TODO: cached import
    module_name, obj_name = dotted_string.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, obj_name)


def init_object(
    obj_dict: dict, /, safe=True, allowed_modules: Optional[Dict[str, Type]] = None
):
    """Initialize an object from a dict

    Note: if the params are also serialized, use `deserialize` instead.

    Args:
        obj_dict: the dict to initialize the object from
        safe: if True, only allowed modules can be imported
        allowed_modules: dict of allowed modules

    Returns:
        the initialized object
    """
    if "__type__" not in obj_dict:
        raise ValueError(
            f"Cannot initialize object from dict {obj_dict}. Missing __type__ key"
        )

    cls = import_dotted_string(
        obj_dict["__type__"], safe=safe, allowed_modules=allowed_modules
    )
    params: dict = {}
    for key, val in obj_dict.items():
        if key == "__type__":
            continue
        params[key] = val

    return cls(**params)


def serialize(value: Any) -> Any:
    """Serialize a value to a JSON-serializable object"""
    if isinstance(value, dict):
        return {key: serialize(val) for key, val in value.items()}

    if isinstance(value, list):
        return [serialize(val) for val in value]

    if isinstance(value, tuple):
        return tuple(serialize(val) for val in value)

    if isinstance(value, NATIVE_TYPE):
        return value

    if inspect.isfunction(value) or inspect.isclass(value):
        if value.__name__ == "<lambda>":
            raise ValueError("Cannot serialize lambda functions")
        return f"{{{{ {value.__module__}.{value.__name__} }}}}"

    if value.__module__ == "builtins":
        return f"{{{{ {value.__module__}.{value.__name__} }}}}"

    if value.__module__ == "typing":
        name = ""
        if hasattr(value, "__name__"):
            name = value.__name__
        elif hasattr(value, "_name"):
            name = value._name
        else:
            raise ValueError(f"Cannot serialize {value}. Unknown name")
        return f"{{{{ {value.__module__}.{name} }}}}"

    if hasattr(value, "__persist_flow__"):
        d = value.__persist_flow__()
        d["__type__"] = f"{value.__class__.__module__}.{value.__class__.__name__}"
        return d

    raise ValueError(
        f"Cannot serialize {value}. Consider implementing __persist_flow__"
    )


def deserialize(
    value: Any, /, safe=True, allowed_modules: Optional[Dict[str, Type]] = None
) -> Any:
    """Deserialize a JSON-serializable object to a Python object"""
    if isinstance(value, str) and value.startswith("{{") and value.endswith("}}"):
        return import_dotted_string(
            value[2:-2].strip(), safe=safe, allowed_modules=allowed_modules
        )

    if isinstance(value, dict) and "__type__" in value:
        cls = import_dotted_string(
            value["__type__"], safe=safe, allowed_modules=allowed_modules
        )
        params: dict = {}
        for key, val in value.items():
            if key == "__type__":
                continue
            params[key] = deserialize(val, safe=safe, allowed_modules=allowed_modules)
        return cls(**params)

    if isinstance(value, dict) and "__type__" not in value:
        return {
            key: deserialize(val, safe=safe, allowed_modules=allowed_modules)
            for key, val in value.items()
        }

    if isinstance(value, list):
        return [
            deserialize(val, safe=safe, allowed_modules=allowed_modules)
            for val in value
        ]

    if isinstance(value, tuple):
        return tuple(
            deserialize(val, safe=safe, allowed_modules=allowed_modules)
            for val in value
        )

    if isinstance(value, NATIVE_TYPE):
        return value

    raise ValueError(f"Cannot deserialize type {type(value)} ({value})")
