"""Default setting for important variables"""
import tempfile

from theflow.utils.paths import default_theflow_path

CONTEXT = {
    "__type__": "theflow.context.Context",
}

CACHE = {
    "__type__": "theflow.cache.FileCache",
    "path": tempfile.mkdtemp(prefix="theflow_"),
}

STORAGE = {
    "__type__": "theflow.storage.LocalStorage",
    "prefix": str(default_theflow_path()),
}
