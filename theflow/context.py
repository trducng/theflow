from typing import Any, Optional

from .settings import settings
from .utils.modules import init_object


class Context:
    """Context to handle communication

    Context is a key-value store backed by a cache that can be used to share
    information between different components in a pipeline. It is also used to store
    information about the pipeline itself.

    Any pipeline synchronization problem is essentially a communication problem. Here
    the context serves as a communication channel and faciliates the communication
    flow easily.

    The context should allow:
    - Global context: shared by all pipelines in all steps in all pipelines
    - Local context: shared by all steps in each pipeline

    The context should be process-safe and can be used in multi-processing environment.
    """

    def __init__(self):
        """Initialize the context"""

        self._cache = init_object(settings.CACHE, safe=False)
        self._global_key = "__global_key__"
        self._cache.set("__global_key__", {})
        self._cache.set("__all_contexts__", [])

    def _is_context_valid(self, context: Optional[str]) -> str:
        """Check if the context name is valid

        Args:
            context: name of the context

        Returns:
            name of the context
        """
        if context is None:
            context = self._global_key

        if not isinstance(context, str):
            raise ValueError(
                f"Context name must be a string or None, got {type(context)}"
            )

        if context not in self._cache:
            raise ValueError(f"Context {context} does not exist")

        return context

    def set(self, name: str, value: Any, context: Optional[str] = None) -> None:
        """Set a value to the context

        Args:
            name: name of the value
            value: value to be set
            context: name of the context, if None (default), use the global context
        """

        context = self._is_context_valid(context)

        with self._cache.lock:
            current = self._cache.get(context, {})
            current[name] = value
            self._cache.set(context, current)

    def get(
        self, name: Optional[str], default=None, context: Optional[str] = None
    ) -> Any:
        """Get a value from the context

        Args:
            name: name of the value. If None, get all values from the context in a dict
            default: default value to return if the value does not exist
            context: name of the context, if None (default), use the global context
        """
        context = self._is_context_valid(context)
        if name is None:
            return self._cache[context]

        return self._cache[context].get(name, default)

    def clear(self, name: Optional[str], context: Optional[str]):
        """Clear a value from the context

        Args:
            name: name of the value. If None, clear all values from the context
            context: name of the context, if None, clear global context
        """
        context = self._is_context_valid(context)
        if name is not None:
            with self._cache.lock:
                current = self._cache[context]
                del current[name]
                self._cache.set(context, current)
        else:
            self._cache.set(context, {})

    def has_context(self, context: str) -> bool:
        """Check if a context exists

        Args:
            context: name of the context

        Returns:
            True if the context exists, False otherwise
        """
        return context in self._cache

    def create_context(self, context: str, exist_ok=False) -> str:
        """Create a context

        Args:
            context: name of the context
            exist_ok: if True, do not raise error if the context already exists

        Returns:
            the string that can be used to access the local context

        Raises:
            ValueError: if the context already exists
        """
        if not isinstance(context, str):
            raise ValueError(f"Context name must be a string, got {type(context)}")

        if context in self._cache:
            if exist_ok:
                return context
            raise ValueError(f"Context {context} already exists")

        with self._cache.lock:
            self._cache.set(context, {})
            all_contexts = self._cache.get("__all_contexts", [])
            all_contexts.append(context)
            self._cache.set("__all_contexts", all_contexts)

        return context

    def get_all_contexts_keys(self) -> list:
        """Get a list of all contexts

        Returns:
            a list of all contexts keys
        """
        return self._cache.get("__all_contexts", [])

    def get_all_contexts(self) -> dict:
        """Get all contexts stored in the cache

        Returns:
            a dict of all contexts
        """
        result = {}
        for key in self.get_all_contexts_keys():
            result[key] = self.get(None, context=key)
        return result
