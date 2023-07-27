from pathlib import Path

from finestflow.base import Composable
from .utils import get_or_create_finestflow_path


def run_id__timestamp(obj: Composable) -> str:
    import time
    return str(int(time.time()))


def store_result__project_root(obj: Composable) -> Path:
    return get_or_create_finestflow_path()
