def test_without_theflow_settings_module(unset_theflow_settings_module):
    """Without environment variable, the settings should be the default"""
    assert unset_theflow_settings_module.CONTEXT == {
        "__type__": "theflow.context.Context"
    }
    assert "SETTING2" not in unset_theflow_settings_module.__dict__
    assert "SETTING3" in unset_theflow_settings_module.__dict__


def test_with_theflow_settings_module(set_theflow_settings_module):
    assert set_theflow_settings_module.CONTEXT == {
        "__type__": "theflow.context.Context",
        "param": "value",
    }
    assert set_theflow_settings_module.SETTING2 == "value2"
    assert "SETTING3" not in set_theflow_settings_module.__dict__
