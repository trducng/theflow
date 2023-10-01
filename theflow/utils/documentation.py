"""Utility modules to extract documentation from the source Compose."""
from __future__ import annotations

import importlib
import inspect
import pkgutil
import sys

from ..base import Compose, Node, Param


def get_compose_documentation(compose: type[Compose]) -> dict:
    """Return the documentation of the compose.

    Returns:
        Dictionary description of the compose, suitable to be parsed. Sample:
            {
                "desc": "Description of the flow",
                "nodes": {
                    "node_1": {
                        "desc": "Description of the node",
                        "type": "Default type of the node",
                        "input": "The input interface",
                        "output": "The output interface"
                    },
                },
                "params": {
                    "param_1": {
                        "desc": "Description of the parameter",
                        "type": "Default type of the parameter",
                        "default": "Default value of the parameter"
                    },
                }
            }
    """
    params, nodes = {}, {}
    for name in dir(compose):
        attr = getattr(compose, name)
        if isinstance(attr, Param):
            params[name] = {
                "desc": attr._help,
                "type": attr._type,
                "default": attr._default,
                "depends_on": attr._depends_on,
            }
        elif isinstance(attr, Node):
            nodes[name] = {
                "desc": attr._help,
                "type": attr._default,
                "input": attr._input,
                "output": attr._output,
                "depends_on": attr._depends_on,
            }

    return {
        "desc": compose.__doc__ or "",
        "params": params,
        "nodes": nodes,
    }


def get_composes_from_module(module_path: str, recursive: bool = True) -> dict:
    """Get all composes from module

    Args:
        module_path: The path to the module

    Returns:
        A dictionary of composes, with the key being the name of the compose and the
        value being the compose class itself.
    """
    composes: dict = {}
    module = sys.modules.get(module_path)
    if not (
        module
        and (spec := getattr(module, "__spec__", None))
        and getattr(spec, "_initializing", False) is False
    ):
        module = importlib.import_module(module_path)

    for name, obj in inspect.getmembers(module):
        if inspect.isclass(obj) and issubclass(obj, Compose) and obj != Compose:
            if not obj.__module__.startswith(module_path):
                # irrelevant import
                continue
            composes[f"{obj.__module__}.{obj.__name__}"] = obj

    if recursive and "__path__" in dir(module):
        for _, name, _ in pkgutil.iter_modules(module.__path__):
            composes.update(
                get_composes_from_module(f"{module_path}.{name}", recursive=True)
            )

    return composes


def get_compose_documentation_from_module(
    module_path: str, recursive: bool = True
) -> dict:
    """Get all composes documenations from module

    Args:
        module_path: The path to the module
        recursive: Whether to recursively search for composes in submodules

    Returns:
        A dictionary of composes, with the key being the name of the compose and the
        value being the compose documentation
    """
    composes = get_composes_from_module(module_path, recursive=recursive)
    return {
        name: get_compose_documentation(compose) for name, compose in composes.items()
    }
