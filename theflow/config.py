from typing import TYPE_CHECKING, Any, Optional, Type, Union

import yaml

if TYPE_CHECKING:
    from .base import Compose

from .utils.modules import import_dotted_string

DEFAULT_CONFIG = {
    # don't store the result if None
    "store_result": "{{ theflow.callbacks.store_result__pipeline_name }}",
    "run_id": "{{ theflow.callbacks.run_id__timestamp }}",
    "compose_name": "{{ theflow.callbacks.compose_name__class_name }}",
}


class ConfigGet:
    """A wrapper class for config retrieval"""

    def __init__(self, config: "Config", pipeline: "Compose"):
        self._config = config
        self._pipeline = pipeline

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._config, name)
        if callable(attr):
            return attr(self._pipeline)
        return attr

    def dump(self) -> dict:
        """Pass-through the config export"""
        return self._config.dump()


class ConfigProperty:
    """Serve as property to access the config from the pipeline instance"""

    def __get__(self, obj: "Compose", obj_type: Type["Compose"]) -> Any:
        if obj._ff_config is None:
            raise ValueError("ConfigProperty can only be accessed after initialization")
        return ConfigGet(obj._ff_config, obj)

    def __set__(self, obj: "Compose", value: Union[dict, "Config", None]) -> None:
        if not isinstance(value, Config):
            raise ValueError("ConfigProperty can only be set with Config object")

        if isinstance(value, Config):
            obj.__dict__["_ff_config"] = value
        elif isinstance(value, dict) or value is None:
            obj.__dict__["_ff_config"] = Config(value, cls=obj.__class__)
        else:
            raise ValueError(
                f"Unknown config type: {type(value)}. Must be dict or Config"
            )


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

    Args:
        config: config dict or path to a yaml file  (default: None)
        cls: the pipeline class (default: None)
    """

    if TYPE_CHECKING:
        from pathlib import Path

        store_result: "Path"
        run_id: str

    def __init__(
        self,
        config: Optional[Union[dict, str]] = None,
        cls: Optional[Type["Compose"]] = None,
    ):
        self._available_configs = set(DEFAULT_CONFIG.keys())

        self.update(DEFAULT_CONFIG)
        if cls is not None:
            self.update(cls)
        if config:
            if isinstance(config, str):
                with open(config) as f:
                    config = yaml.safe_load(f)
            self.update(config)

    def update_from_dict(self, config: dict):
        """Parse the config dict"""
        for key, value in config.items():
            if key.startswith("__"):
                continue

            if key not in self._available_configs:
                raise ValueError(f"Unknown config: {key}")

            if (
                isinstance(value, str)
                and value.startswith("{{")
                and value.endswith("}}")
            ):
                # parse to the callback function
                dotted_string = value[2:-2].strip()
                # TODO: handle safe import
                value = import_dotted_string(dotted_string, safe=False)

            setattr(self, key, value)

    def update_from_pipeline(self, cls: Type["Compose"]) -> None:
        """Parse the pipeline configs from pipeline.Config"""
        classes = cls.mro()
        for each_cls in reversed(classes):
            if hasattr(each_cls, "Config"):
                self.update_from_dict(each_cls.Config.__dict__)

    def update_from_config(self, config: "Config") -> None:
        """Parse the pipeline configs from another Config instance"""
        self.update_from_dict(config.dump())

    def update(self, val: Any) -> None:
        from .base import Compose

        if isinstance(val, dict):
            self.update_from_dict(val)
        elif isinstance(val, type) and issubclass(val, Compose):
            self.update_from_pipeline(val)
        elif isinstance(val, Config):
            self.update_from_config(val)
        else:
            raise ValueError(f"Unknown config type: {type(val)}")

    def dump(self) -> dict:
        """Export the config dict"""
        output = {}
        for key in self._available_configs:
            if callable(getattr(self, key)):
                obj = getattr(self, key)
                output[key] = f"{{{{ {obj.__module__}.{obj.__name__} }}}}"
            else:
                output[key] = getattr(self, key)

        return output
