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


def test_without_theflow_settings_module(unset_theflow_settings_module):
    """Without environment variable, the settings should be the default"""
    assert unset_theflow_settings_module.CONTEXT == {
        "__type__": "theflow.context.Context"
    }
    assert "SETTING2" not in unset_theflow_settings_module.__dict__


def test_with_theflow_settings_module(set_theflow_settings_module):
    assert set_theflow_settings_module.CONTEXT == {
        "__type__": "theflow.context.Context",
        "param": "value",
    }
    assert set_theflow_settings_module.SETTING2 == "value2"
