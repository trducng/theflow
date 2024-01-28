from .base import BaseCache


class PyMemcacheCache(BaseCache):
    def __init__(self, servers, **kwargs):
        try:
            import pymemcache  # type: ignore
        except ImportError:
            raise ImportError(
                "The pymemcache package is required to use the PyMemcacheCache. "
                "Please run: pip install pymemcache"
            )

        self._cache = pymemcache.Client(servers, **kwargs)
