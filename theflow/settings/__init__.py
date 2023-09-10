import os

from . import default


class Settings:
    """Setting module can be set with environment variable THEFLOW_SETTINGS_MODULE"""

    def __init__(self):
        """Set the setting"""
        for setting in dir(default):
            if setting.isupper():
                setattr(self, setting, getattr(default, setting))
        if (
            "THEFLOW_SETTINGS_MODULE" in os.environ
            and os.environ["THEFLOW_SETTINGS_MODULE"]
        ):
            import importlib

            module = importlib.import_module(os.environ["THEFLOW_SETTINGS_MODULE"])
            for setting in dir(module):
                if setting.isupper():
                    setattr(self, setting, getattr(module, setting))

    def __getattr__(self, item):
        """Get the setting"""
        name = item.upper()
        if name not in self.__dict__:
            raise AttributeError(f"Setting {name} not found")

        return getattr(self, name)


settings = Settings()
