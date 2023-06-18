from typing import Any, Optional, Type, Union, TYPE_CHECKING

import yaml 

if TYPE_CHECKING:
    from .pipeline import Pipeline
from .utils import import_dotted_string


DEFAULT_CONFIG = {
    # don't store the result if None
    "store_result": "{{ finestflow.callbacks.store_result__project_root }}",
    "run_id": "{{ finestflow.callbacks.run_id__timestamp }}",
}


class ConfigGet:
    """A wrapper class for config retrieval"""

    def __init__(self, config: "Config", pipeline: "Pipeline"):
        self._config = config
        self._pipeline = pipeline

    def __getattr__(self, name: str) -> Any:
        attr = getattr(self._config, name)
        if callable(attr):
            return attr(self._pipeline)
        return attr


class ConfigProperty:
    """Serve as property to access the config from the pipeline instance"""

    def __get__(self, obj: "Pipeline", obj_type: Type["Pipeline"]) -> Any:
        return ConfigGet(obj._ff_config, obj)


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

    def __init__(
        self,
        config: Optional[Union[dict, str]] = None,
        cls: Optional[Type["Pipeline"]] = None
    ):
        self._available_configs = set(DEFAULT_CONFIG.keys())

        self.update(DEFAULT_CONFIG)
        if cls is not None:
            self.update(cls)
        if config:
            if isinstance(config, str):
                with open(config, "r") as f:
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
                value = import_dotted_string(dotted_string)

            setattr(self, key, value)

    def update_from_pipeline(self, cls: Type["Pipeline"]) -> None:
        """Parse the pipeline configs from pipeline.Config"""
        classes = cls.mro()
        for cls in reversed(classes):
            if hasattr(cls, "Config"):
                self.update_from_dict(cls.Config.__dict__)

    def update_from_config(self, config: "Config") -> None:
        """Parse the pipeline configs from another Config instance"""
        self.update_from_dict(config.export())

    def update(self, val: Any) -> None:
        from .pipeline import Pipeline
        if isinstance(val, dict):
            self.update_from_dict(val)
        elif isinstance(val, type) and issubclass(val, Pipeline):
            self.update_from_pipeline(val)
        elif isinstance(val, Config):
            self.update_from_config(val)
        else:
            raise ValueError(f"Unknown config type: {type(val)}")

    def export(self) -> dict:
        """Export the config dict"""
        output = {}
        for key in self._available_configs:
            if callable(getattr(self, key)):
                obj = getattr(self, key)
                output[key] = f"{{{{ {obj.__module__}.{obj.__name__} }}}}"
            else:
                output[key] = getattr(self, key)

        return output