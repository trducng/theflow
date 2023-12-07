import tempfile
from pathlib import Path

from theflow.settings.default import *  # noqa: F401,F403

CACHE = {
    "__type__": "theflow.cache.FileCache",
    "path": str(Path(tempfile.mkdtemp(prefix="theflow_"), "cache")),
}
