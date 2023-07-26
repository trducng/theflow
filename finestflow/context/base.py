"""Context base class.

Context is a key-value store that can be used to share information between
different components in a pipeline. It is also used to store information
about the pipeline itself.

Any pipeline synchronization problem is essentially a communication problem. Here
the context serves as a communication channel and faciliate the communication
flow easily.

The context should allow:
- Global context: shared by all pipelines in all steps in all pipelines
- Local context: shared by all steps in each pipeline
"""
import abc
from typing import Any, Optional


class BaseContext(abc.ABC):
    @abc.abstractmethod
    def set(self, name: str, value: Any, context: Optional[str] = None) -> None:
        """Set a value to the context

        Args:
            name: name of the value
            value: value to be set
            context: name of the context, if None (default), use the global context
        """
        ...

    @abc.abstractmethod
    def get(
        self, name: Optional[str], default: Any = None, context: Optional[str] = None
    ) -> Any:
        """Get a value from the context

        Args:
            name: name of the value. If None, get all values from the context in a dict
            context: name of the context, if None (default), use the global context
        """
        ...

    @abc.abstractmethod
    def clear(self, name: Optional[str], context: Optional[str], force: bool):
        """Clear a value from the context

        Args:
            name: name of the value. If None, clear all values from the context
            context: name of the context, if None, clear global context
        """
        ...

    @abc.abstractmethod
    def clear_all(self):
        """Clear all values from all contexts"""
        ...

    @abc.abstractmethod
    def create_local_context(self, context: str, exist_ok=False) -> str:
        """Create a local context

        Args:
            context: name of the local context
            exist_ok: if True, do not raise error if the context already exists

        Returns:
            the string that can be used to access the local context

        Raises:
            ValueError: if the context already exists
        """
        ...


