import pytest

from theflow import Compose, Node, Param
from theflow.utils.modules import ObjectInitDeclaration


class ComplexObj:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class FlowA(Compose):
    x: int = -1
    param_a = Param(default=-2)
    node_a: Compose

    def run(self):
        return self.x + self.node_a()


class FlowB(Compose):
    x: int
    param_b = Param(default=ObjectInitDeclaration(ComplexObj, x=20, y=30))
    node_b: Node[Compose] = Node(default=FlowA.withx(x=0))

    def run(self):
        return self.x + self.node_b()


class FlowC1(Compose):
    x: int
    node_c: Node[Compose] = Node(
        default=FlowB.withx(
            x=9,
            param_b=FlowB.param_b._default.withx(x=2, y=3),
            node_b=FlowA.withx(x=10),
        )
    )

    def run(self):
        return self.x + self.node_c()


class FlowC2(Compose):
    x: int
    node_c: Node[Compose] = Node(default=FlowB)

    def run(self):
        return self.x + self.node_c()


def test_default_node_param():
    flowc1 = FlowC1(x=1)
    assert flowc1.x == 1
    assert flowc1.node_c.node_b.param_a == -2
    assert flowc1.node_c.x == 9
    assert flowc1.node_c.node_b.x == 10
    assert flowc1.node_c.param_b.x == 2
    assert isinstance(flowc1.node_c.param_b, ComplexObj)
    assert isinstance(flowc1.node_c, FlowB)
    assert isinstance(flowc1.node_c.node_b, FlowA)

    flowc2 = FlowC2(x=2)
    assert flowc2.x == 2
    assert isinstance(flowc2.node_c, FlowB)
    with pytest.raises(AttributeError):
        # FlowB doesn't have default x
        flowc2.node_c.x
    assert flowc2.node_c.node_b.x == 0
    assert flowc2.node_c.param_b.x == 20
    assert isinstance(flowc2.node_c.param_b, ComplexObj)

    flowa = FlowA()
    assert flowa.x == -1


class SubclassC2(FlowC2):
    node_c: Node[Compose] = Node(default=FlowA.withx(x=11))


def test_subclass_flow():
    scflowc2a = SubclassC2(x=3)
    assert scflowc2a.x == 3
    assert isinstance(scflowc2a.node_c, FlowA)
    assert scflowc2a.node_c.x == 11

    scflowc2b = SubclassC2({"node_c.x": 12}, x=4)
    assert scflowc2b.x == 4
    assert isinstance(scflowc2b.node_c, FlowA)
    assert scflowc2b.node_c.x == 12


class TestParamCallback:
    class Flow(Compose):
        x: int = 2

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._z_call_counted = 0

        def run(self):
            ...

        @Param.default()
        def y(self):
            """If y is not set, it will be 2 * x"""
            return self.x * 2

        @Param.auto()
        def z(self):
            """If z is not set, it will be 3 * y"""
            self._z_call_counted += 1
            return self.y * 3

    class FlowDepend(Compose):
        x: int = 2

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._z_call_counted = 0

        def run(self):
            ...

        @Param.default()
        def y(self):
            """If y is not set, it will be 2 * x"""
            return self.x * 2

        @Param.auto(depends_on=["y"])
        def z(self):
            """If z is not set, it will be 3 * y"""
            self._z_call_counted += 1
            return self.y * 3

    class FlowNoCache(Compose):
        x: int = 2

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._z_call_counted = 0

        def run(self):
            ...

        @Param.default()
        def y(self):
            """If y is not set, it will be 2 * x"""
            return self.x * 2

        @Param.auto(cache=False)
        def z(self):
            """If z is not set, it will be 3 * y"""
            self._z_call_counted += 1
            return self.y * 3

    def test_param_default_callback(self):
        flow1 = self.Flow()
        assert flow1.y == 4
        flow1.x = 3
        assert flow1.y == 4
        flow1.y = 10
        assert flow1.y == 10

        flow2 = self.Flow(x=3)
        assert flow2.y == 6

    def test_param_auto_callback(self):
        flow = self.Flow()

        # z is calculated from y
        assert flow.z == 12
        assert flow._z_call_counted == 1

        # Changing y make recalculate z
        flow.y = 3
        assert flow.z == 9
        assert flow._z_call_counted == 2

        # Not other param change, z is cached
        assert flow.z == 9
        assert flow._z_call_counted == 2

        # Changing x not affect z but still make recalculate z
        flow.x = 10
        assert flow.z == 9
        assert flow._z_call_counted == 3

        # Setting z directly is not allowed
        with pytest.raises(ValueError):
            flow.z = 10

    def test_param_auto_callback_with_depend_on(self):
        flow = self.FlowDepend()

        # z is calculated from y
        assert flow.z == 12
        assert flow._z_call_counted == 1

        # Changing x not affect z and now doesn't make recalculate z
        flow.x = 10
        assert flow.z == 12
        assert flow._z_call_counted == 1

        # Changing y still make recalculate z
        flow.y = 3
        assert flow.z == 9
        assert flow._z_call_counted == 2

    def test_param_auto_callback_with_cache_disabled(self):
        flow = self.FlowNoCache()

        # z is calculated from y
        assert flow.z == 12
        assert flow._z_call_counted == 1

        # just accessing z force a recalculate
        assert flow.z == 12
        assert flow._z_call_counted == 2
