from hashlib import md5
from typing import Any


class naivehash:
    """Hash a Python object

    Args:
        hash_func: hash function to use. Default is md5
    """

    def __init__(self, hash_func=None):
        """Initialize the hash object"""
        self.hash_func = hash_func() if hash_func is not None else md5()

    def update(self, obj: Any):
        """Hash a Python object

        Args:
            obj: Python object to be hashed

        Returns:
            hash of the object
        """
        if isinstance(obj, (str, int, float, bool)):
            self.hash_func.update(str(obj).encode())
        elif isinstance(obj, (tuple, list)):
            for item in obj:
                self.update(item)
        elif isinstance(obj, dict):
            for key in sorted(obj):
                self.update(key)
                self.update(obj[key])
        else:
            for attr in dir(obj):
                if attr.startswith("_"):
                    continue
                self.update(attr)
                self.update(getattr(obj, attr))

    def __call__(self, obj: Any) -> str:
        """Return the hash digest"""
        self.update(obj)
        return self.hash_func.hexdigest()
