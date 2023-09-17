"""Default setting for important variables"""
from theflow.utils.paths import default_theflow_path

CONTEXT = {
    "__type__": "theflow.context.Context",
}

CACHE = {
    "__type__": "theflow.cache.MemoryCache",
}

STORAGE = {
    "__type__": "theflow.storage.LocalStorage",
    "prefix": str(default_theflow_path()),
}
