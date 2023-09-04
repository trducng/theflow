import time
from pathlib import Path

from theflow.base import Compose

from .utils.paths import get_or_create_theflow_path


def run_id__timestamp(obj: Compose) -> str:
    return str(time.time()).replace(".", "")


def store_result__project_root(obj: Compose) -> Path:
    return get_or_create_theflow_path()
