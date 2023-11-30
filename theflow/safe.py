"""Construct a flow declaratively in a safe manner."""
import logging
from typing import Dict, Optional, Type

from .base import Function
from .utils.modules import deserialize

logger = logging.getLogger(__name__)

load = deserialize


def create(
    obj: dict,
    /,
    safe=True,
    allowed_modules: Optional[Dict[str, Type]] = None,
) -> Optional[Type[Function]]:
    pass
