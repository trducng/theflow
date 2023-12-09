import pytest

from theflow import Function, Node, Param, lazy, unset
from theflow.debug import has_cyclic_dependency
from theflow.exceptions import CyclicDependencyError


class ComplexObj:
    def __init__(self, x, y):
        self.x = x
        self.y = y


class FlowA(Function):
    x: int = -1
    param_a: int = -2
    node_a: Function

    def run(self):
        return self.x + self.node_a()


class FlowB(Function):
    x: int
    param_b: ComplexObj = Param(default=lazy(ComplexObj, x=20, y=30))
    node_b: Function = FlowA.withx(x=0)

    def run(self):
        return self.x + self.node_b()


class FlowC1(Function):
    x: int
    node_c: Function = Node(
        default=FlowB.withx(
            x=9,
            param_b=FlowB.param_b._default.withx(x=2, y=3),
            node_b=FlowA.withx(x=10),
        )
    )

    def run(self):
        return self.x + self.node_c()


class FlowC2(Function):
    x: int
    node_c: Function = Node(default=FlowB)

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
    assert flowc2.node_c.x == unset
    assert flowc2.node_c.node_b.x == 0
    assert flowc2.node_c.param_b.x == 20
    assert isinstance(flowc2.node_c.param_b, ComplexObj)

    flowa = FlowA()
    assert flowa.x == -1


class SubclassC2(FlowC2):
    node_c: Function = FlowA.withx(x=11)


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
    class Flow(Function):
        x: int = 2
        y: int = Param(default_callback=lambda obj: obj.x * 2)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._z_call_counted = 0

        def run(self):
            ...

        @Param.auto()
        def z(self):
            """If z is not set, it will be 3 * y"""
            self._z_call_counted += 1
            return self.y * 3

    class FlowDepend(Function):
        x: int = 2
        y: int = Param(default_callback=lambda obj: obj.x * 2)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._z_call_counted = 0

        def run(self):
            ...

        @Param.auto(depends_on=["y"])
        def z(self):
            """If z is not set, it will be 3 * y"""
            self._z_call_counted += 1
            return self.y * 3

    class FlowNoCache(Function):
        x: int = 2
        y: int = Param(default_callback=lambda obj: obj.x * 2)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._z_call_counted = 0

        def run(self):
            ...

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


class TestCircularNodeParamDependency:
    def test_has_cyclic_dependency_single_hop(self):
        class A(Function):
            @Param.auto(depends_on=["y"])
            def x(self) -> int:
                return self.y + 1

            @Param.auto(depends_on=["x"])
            def y(self) -> int:
                return self.x + 1

            def run(self):
                return self.x + self.y

        has_cycle = has_cyclic_dependency(A)
        assert has_cycle

    def test_has_cyclic_dependency_multiple_hops(self):
        class A(Function):
            @Param.auto(depends_on=["y"])
            def x(self) -> int:
                return self.y + 1

            @Param.auto(depends_on=["z"])
            def y(self) -> int:
                return self.z + 1

            @Param.auto(depends_on=["x"])
            def z(self) -> int:
                return self.x + 1

            @Param.auto(depends_on=["y"])
            def w(self) -> int:
                return self.y + 1

            def run(self):
                return self.x + self.y + self.z

        has_cycle = has_cyclic_dependency(A)
        assert has_cycle

    def test_dont_has_cyclic_dependency(self):
        class A(Function):
            w: int

            @Param.auto(depends_on=["y"])
            def x(self) -> int:
                return self.y + 1

            @Param.auto(depends_on=["z"])
            def y(self) -> int:
                return self.z + 1

            @Param.auto(depends_on=["w"])
            def z(self) -> int:
                return self.w + 1

            def run(self):
                return self.x + self.y + self.z

        has_cycle = has_cyclic_dependency(A)
        assert not has_cycle

    def test_has_cycle_at_runtime_single_hop(self):
        class A(Function):
            @Param.auto(depends_on=["y"])
            def x(self) -> int:
                return self.y + 1

            @Param.auto(depends_on=["x"])
            def y(self) -> int:
                return self.x + 1

            def run(self):
                return self.x + self.y

        a = A()
        with pytest.raises(CyclicDependencyError):
            a.x

    def test_has_cycle_at_runtime_multiple_hops(self):
        class A(Function):
            @Param.auto(depends_on=["y"])
            def x(self) -> int:
                return self.y + 1

            @Param.auto(depends_on=["z"])
            def y(self) -> int:
                return self.z + 1

            @Param.auto(depends_on=["x"])
            def z(self) -> int:
                return self.x + 1

            @Param.auto(depends_on=["y"])
            def w(self) -> int:
                return self.y + 1

            def run(self):
                return self.x + self.y + self.z

        a = A()
        with pytest.raises(CyclicDependencyError):
            a.w

    def test_dont_raise_cycle_error_for_valid_function(self):
        class A(Function):
            w: int

            @Param.auto(depends_on=["y"])
            def x(self) -> int:
                return self.y + 1

            @Param.auto(depends_on=["z"])
            def y(self) -> int:
                return self.z + 1

            @Param.auto(depends_on=["w"])
            def z(self) -> int:
                return self.w + 1

            def run(self):
                return self.x + self.y + self.z

        a = A(w=20)
        assert a.x == 23
