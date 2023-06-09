import abc
from typing import Any


class BaseContext(abc.ABC):

    @abc.abstractmethod
    def set(self, name: str, value: Any) -> None:
        """Set a value to the context"""
        ...

    @abc.abstractmethod
    def get(self, name: Any) -> Any:
        """Get a value from the context"""
        ...
