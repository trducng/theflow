import pytest

import theflow.settings


@pytest.fixture(scope="function", autouse=False)
def unset_theflow_settings_module(monkeypatch):
    """Clean THEFLOW_SETTING_MODULE environment variable"""
    monkeypatch.setenv("THEFLOW_SETTINGS_MODULE", "")
    theflow.settings.settings = theflow.settings.Settings()
    from theflow.settings import settings

    yield settings
    monkeypatch.setenv("THEFLOW_SETTINGS_MODULE", "")
    theflow.settings.settings = theflow.settings.Settings()


@pytest.fixture(scope="function", autouse=False)
def set_theflow_settings_module(monkeypatch):
    """Set THEFLOW_SETTING_MODULE environment variable"""
    monkeypatch.setenv("THEFLOW_SETTINGS_MODULE", "tests.assets.temporary_settings")
    theflow.settings.settings = theflow.settings.Settings()
    from theflow.settings import settings

    yield settings
    monkeypatch.setenv("THEFLOW_SETTINGS_MODULE", "")
    theflow.settings.settings = theflow.settings.Settings()