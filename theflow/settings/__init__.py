import os
import sys
from pathlib import Path

from . import default


class Settings:
    """A lazy setting module, will be initialized when first accessed

    Setting module can be set from this priority:
        1. with environment variable THEFLOW_SETTINGS_MODULE
        2. with flowsettings.py in current working directory
        3. with flowsettings.py in sys.path
        4. with default settings specified in this package
    """

    def __init__(self):
        """Set the setting"""
        self._initialized = False

    def load_settings(self):
        self._initialized = True

        if (
            "THEFLOW_SETTINGS_MODULE" in os.environ
            and os.environ["THEFLOW_SETTINGS_MODULE"]
        ):
            import importlib

            module = importlib.import_module(os.environ["THEFLOW_SETTINGS_MODULE"])
            for setting in dir(module):
                if setting.isupper():
                    setattr(self, setting, getattr(module, setting))
            return

        flowsettings_acceptable_dirs: list[str] = [os.getcwd()] + sys.path
        for flowsettings_dir in flowsettings_acceptable_dirs:
            flowsettings_path = Path(flowsettings_dir) / "flowsettings.py"
            if flowsettings_path.exists():
                import importlib.util

                spec = importlib.util.spec_from_file_location(
                    "flowsettings", flowsettings_path
                )

                if spec is None or spec.loader is None:
                    continue

                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                for setting in dir(module):
                    if setting.isupper():
                        setattr(self, setting, getattr(module, setting))
                return

        for setting in dir(default):
            if setting.isupper():
                setattr(self, setting, getattr(default, setting))

    def __getattr__(self, item):
        """Get the setting"""
        if not self._initialized:
            self.load_settings()

        name = item.upper()
        if name not in self.__dict__:
            raise AttributeError(f"Setting {name} not found")

        return getattr(self, name)


settings = Settings()
