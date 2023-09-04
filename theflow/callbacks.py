import time
from pathlib import Path

from theflow.base import Composable

from .utils.paths import get_or_create_theflow_path


def run_id__timestamp(obj: Composable) -> str:
    return str(time.time()).replace(".", "")


def store_result__project_root(obj: Composable) -> Path:
    return get_or_create_theflow_path()
