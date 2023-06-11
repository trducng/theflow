from typing import Any, Optional, Type

from finestflow import Pipeline
from .utils import import_dotted_string


DEFAULT_CONFIG = {
    # don't store the result if None
    "store_result": "{{ finestflow.callbacks.store_result__project_root }}",
    "run_id": "{{ finestflow.callbacks.run_id__timestamp }}",
}


class Config:
    """Config for the pipeline

    Config is a dict-like object that stores the configs for the pipeline. The config
    resolution order is:
        1. default config
        2. pipeline.Config from parent classes to child classes in reverse MRO order
        3. config passed to the constructor

    Each value for a config can either be a scalar value, or a string to a callback
    function that takes the pipeline instance as the only argument. The callback
    function will be called when the config is accessed. The string to the callback
    function should be in the format of `{{ module.to.function }}`.
    """

    def __init__(
        self, config: Optional[dict] = None, cls: Optional[Type[Pipeline]] = None
    ):
        self._available_configs = set(DEFAULT_CONFIG.keys())

        self.update(DEFAULT_CONFIG)
        if cls:
            self.update(cls)
        if config:
            self.update(config)

    def parse_callbacks(self) -> None:
        """Parse the callbacks"""
        for key in self._available_configs:
            value = getattr(self, key)
            if (
                isinstance(value, str)
                and value.startswith("{{")
                and value.endswith("}}")
            ):
                dotted_string = value[2:-2].strip()
                func = import_dotted_string(dotted_string)
                setattr(self, key, func)

    def update_from_dict(self, config: dict):
        """Parse the config dict"""
        for key, value in config.items():
            if key.startswith("__"):
                continue

            if key not in self._available_configs:
                raise ValueError(f"Unknown config: {key}")

            setattr(self, key, value)

    def update_from_pipeline(self, cls: Type[Pipeline]) -> None:
        """Parse the pipeline configs from pipeline.Config"""
        classes = cls.mro()
        for cls in reversed(classes):
            if hasattr(cls, "Config"):
                self.update_from_dict(cls.Config.__dict__)

    def update(self, val: Any) -> None:
        if isinstance(val, dict):
            self.update_from_dict(val)
        elif isinstance(val, type) and issubclass(val, Pipeline):
            self.update_from_pipeline(val)
        else:
            raise ValueError(f"Unknown config type: {type(val)}")