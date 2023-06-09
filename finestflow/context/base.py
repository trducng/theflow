import abc
from typing import Any, Optional


class BaseContext(abc.ABC):

    @abc.abstractmethod
    def set(self, name: str, value: Any) -> None:
        """Set a value to the context
        
        Args:
            name: name of the value
            value: value to be set
        """
        ...

    @abc.abstractmethod
    def get(self, name: Optional[str]) -> Any:
        """Get a value from the context

        Args:
            name: name of the value. If None, get all values from the context in a dict
        """
        ...

    @abc.abstractmethod
    def clear(self, name: Optional[str]) -> None:
        """Clear a value from the context

        Args:
            name: name of the value. If None, clear all values from the context
        """
        ...