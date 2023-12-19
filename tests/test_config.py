import pytest

from theflow import Function


class Level2Function(Function):
    param1: int
    param2: int = 20

    class Config:
        allow_extra = True

    def run(self, x):
        return self.param1 + self.param2 + x


class Level1Function(Function):
    param1: int = 1
    node: Function

    def run(self, x):
        return self.param1 + self.node(x)


class RootFunction(Function):
    param1: int = 20
    node: Function

    class Config:
        allow_extra = True
        params_publish = True

    def run(self, x):
        return self.param1 + self.node(x)

    def _runx(self, *args, **kwargs):
        """Intervene to not delete the shared params for testing purpose"""
        self.fl.in_run = True
        shared_params = kwargs.pop("shared_params")
        out = self.run(*args, **kwargs)
        shared_params.update(
            self.context.get(
                None,
                context=f"{self.fl.flow_qualidx}|published_params",
            )
        )
        return out


class TestPublishSubscribe:
    def test_pubsub_no_extraparam(self):
        root = RootFunction(node=Level1Function(node=Level2Function()))
        shared_params = {}
        output = root(1, shared_params=shared_params)

        assert output == 62, "Only update level2/param1, not level1/param1"
        assert shared_params == {"param1": 20}, "Only param1 is published"

    def test_pubsub_extraparam(self):
        root = RootFunction(
            node=Level1Function(node=Level2Function()),
            param2=30,
        )
        shared_params = {}
        output = root(1, shared_params=shared_params)

        assert output == 62
        assert shared_params == {"param1": 20, "param2": 30}, "Extra param2 is passed"

    def test_pubsub_all_params_are_set(self):
        root = RootFunction(node=Level1Function(node=Level2Function(param1=100)))
        shared_params = {}
        output = root(1, shared_params=shared_params)

        assert (
            output == 142
        ), "Level2/param1 shouldn't be updated because it is \
            explicitly set"
        assert shared_params == {"param1": 20}, "Only param1 is published"


class TestAllowExtra:
    def test_allow_extra_true(self):
        func = Level2Function(param1=10, param2=20, param3=30)
        assert func.param1 == 10
        assert func.param3 == 30
        assert len(func.params) == 2, "Still param3 isn't officially counted as param"
        assert func._attrx["AllowExtraParam"] == {"param3": 30}

    def test_allow_extra_false(self):
        with pytest.raises(AttributeError):
            Level1Function(param1=10, param2=20)
