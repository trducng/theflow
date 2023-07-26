from pathlib import Path

from finestflow.pipeline import Pipeline
from .utils import get_or_create_finestflow_path


def run_id__timestamp(obj: Pipeline) -> str:
    import time
    return str(int(time.time()))


def store_result__project_root(obj: Pipeline) -> Path:
    return get_or_create_finestflow_path()
