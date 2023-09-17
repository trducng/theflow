import time

from theflow.base import Compose


def run_id__timestamp(obj: Compose) -> str:
    return str(time.time()).replace(".", "")


def store_result__pipeline_name(obj: Compose) -> str:
    return f"{obj.__module__}.{obj.__class__.__qualname__}"


def compose_name__class_name(obj: Compose) -> str:
    return f"{obj.__class__.__module__}.{obj.__class__.__qualname__}"
