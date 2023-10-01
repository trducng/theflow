from ..settings import settings
from ..utils.modules import init_object
from .local import LocalStorage

# make this lazy (created during first request)
storage = init_object(settings.STORAGE, safe=False)

__all__ = ["LocalStorage", "storage"]
