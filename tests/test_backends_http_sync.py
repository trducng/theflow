from theflow.backends.http_sync import local_only_func_def

SAMPLE = {
    "function": "func1",
    "params": {"a": 1, "b": 2},
    "nodes": {
        "x1": {
            "function": "funcx1",
            "params": {"c": 3},
            "nodes": {},
            "configs": {"default_backend": {"__type__": "theflow.backends.Backend"}},
        },
        "x2": {
            "function": "funcx2",
            "params": {"d": 4},
            "nodes": {
                "y1": {
                    "function": "funcy1",
                    "params": {"e": 5},
                    "nodes": {},
                    "configs": {
                        "default_backend": {"__type__": "theflow.backends.Backend"}
                    },
                },
            },
            "configs": {
                "default_backend": {
                    "__type__": "theflow.backends.HttpSyncBackend",
                    "endpoint": "http://localhost:8000",
                }
            },
        },
    },
    "configs": {"default_backend": {"__type__": "theflow.backends.Backend"}},
}


def test_local_only_func_def():
    func_def = local_only_func_def(SAMPLE)
    ref = {
        "function": "func1",
        "params": {"a": 1, "b": 2},
        "nodes": {
            "x1": {
                "function": "funcx1",
                "params": {"c": 3},
                "nodes": {},
                "configs": {
                    "default_backend": {"__type__": "theflow.backends.Backend"}
                },
            },
            "x2": {
                "function": "funcx2",
                "params": {"d": 4},
                "nodes": {},
                "configs": {
                    "default_backend": {
                        "__type__": "theflow.backends.HttpSyncBackend",
                        "endpoint": "http://localhost:8000",
                    }
                },
            },
        },
        "configs": {"default_backend": {"__type__": "theflow.backends.Backend"}},
    }
    assert func_def == ref
