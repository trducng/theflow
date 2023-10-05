from unittest import TestCase

import pytest

from theflow import Compose, Node, Param, load

from .assets.sample_flow import Func, Multiply, Sum1, Sum2, callback


class TestComposeSaveAndLoad(TestCase):
    def test_save_ignore_depend_as_default(self):
        """By default, ignore_depends for the output"""
        obj = Func(a=20, e=20, x=Sum1(a=20))
        d = obj.dump()
        self.assertEqual(
            d,
            {
                "type": "tests.assets.sample_flow.Func",
                "params": {"a": 20, "e": 20, "f": 40},
                "nodes": {
                    "m": {
                        "type": "tests.assets.sample_flow.Sum2",
                        "params": {"a": 100},
                        "nodes": {
                            "mult": {
                                "nodes": {},
                                "params": {"a": 10},
                                "type": "tests.assets.sample_flow.Multiply",
                            }
                        },
                    },
                    "x": {
                        "type": "tests.assets.sample_flow.Sum1",
                        "params": {"a": 20, "b": 10, "c": 10},
                        "nodes": {},
                    },
                    "y": {
                        "type": "tests.assets.sample_flow.Sum1",
                        "params": {"a": 100, "b": 10, "c": 10},
                        "nodes": {},
                    },
                },
            },
        )

    def test_save_no_ignore_depends(self):
        """Include params and nodes with ignore_depends"""
        obj = Func(a=20, e=20, x=Sum1(a=20))
        d = obj.dump(ignore_depends=False)
        self.assertEqual(
            d,
            {
                "type": "tests.assets.sample_flow.Func",
                "params": {"a": 20, "e": 20, "f": 40},
                "nodes": {
                    "m": {
                        "type": "tests.assets.sample_flow.Sum2",
                        "params": {"a": 100},
                        "nodes": {
                            "mult": {
                                "nodes": {},
                                "params": {"a": 10},
                                "type": "tests.assets.sample_flow.Multiply",
                            }
                        },
                    },
                    "x": {
                        "type": "tests.assets.sample_flow.Sum1",
                        "params": {"a": 20, "b": 10, "c": 10, "d": 20},
                        "nodes": {},
                    },
                    "y": {
                        "type": "tests.assets.sample_flow.Sum1",
                        "params": {"a": 100, "b": 10, "c": 10, "d": 20},
                        "nodes": {},
                    },
                    "z": {
                        "type": "tests.assets.sample_flow.Sum1",
                        "params": {"a": 200, "b": 10, "c": 10, "d": 20},
                        "nodes": {},
                    },
                },
            },
        )

    def test_load_successfully_unsafe(self):
        """By default, ignore_depends for the output"""
        obj = Func(a=20, e=20, x=Sum1(a=20))
        d = obj.dump()
        obj2 = load(d, safe=False)
        self.assertEqual(obj.dump(), obj2.dump())

    def test_load_safe_without_module_raise_error(self):
        """Raise error if without supplied modules"""
        obj = Func(a=20, e=20, x=Sum1(a=20))
        d = obj.dump()
        with self.assertRaises(ValueError):
            load(d)

    def test_load_safe_missing_module_raise_error(self):
        """Raise error if without supplied modules"""
        obj = Func(a=20, e=20, x=Sum1(a=20))
        d = obj.dump()
        with self.assertRaises(ValueError):
            load(d, allowed_modules={"tests.assets.sample_flow.Func": Func})

    def test_load_safe_with_module(self):
        """Raise error if without supplied modules"""
        obj = Func(a=20, e=20, x=Sum1(a=20))
        d = obj.dump()
        obj2 = load(
            d,
            allowed_modules={
                "tests.assets.sample_flow.Sum1": Sum1,
                "tests.assets.sample_flow.Sum2": Sum2,
                "tests.assets.sample_flow.callback": callback,
                "tests.assets.sample_flow.Func": Func,
                "tests.assets.sample_flow.Multiply": Multiply,
            },
        )
        self.assertEqual(obj.dump(), obj2.dump())

    def test_persist_flow(self):
        """Represent flow in a serialiable way that can be init later"""
        obj = Func(a=20, e=20, x=Sum1(a=20))
        persisted = obj.__persist_flow__()
        self.assertEqual(
            persisted,
            {
                "__type__": "tests.assets.sample_flow.Func",
                "a": 20,
                "e": 20,
                "f": 40,
                "m": {
                    "__type__": "tests.assets.sample_flow.Sum2",
                    "a": 100,
                    "mult": {"__type__": "tests.assets.sample_flow.Multiply", "a": 10},
                },
                "x": {
                    "__type__": "tests.assets.sample_flow.Sum1",
                    "a": 20,
                    "b": 10,
                    "c": 10,
                },
                "y": {
                    "__type__": "tests.assets.sample_flow.Sum1",
                    "a": 100,
                    "b": 10,
                    "c": 10,
                },
            },
        )


class ExtraNodeParam(Compose):
    param_a = Param(help="Param A", data1=1, data2="2")
    node_a: Node[Compose] = Node(help="Node A", data1=1, data2="2")

    @Node.decorate(data3={"sample": 1}, depends_on=["node_a"])
    def node_b(self):
        return Compose()

    @Param.decorate(data3={"sample": 1}, depends_on=["node_a"])
    def param_b(self):
        return 1


class TestNode(TestCase):
    def test_node_extra_info(self):
        """Add extra data to the node"""
        self.assertEqual(ExtraNodeParam.node_a._extras["data1"], 1)
        self.assertEqual(ExtraNodeParam.node_b._extras["data3"], {"sample": 1})

        self.assertEqual(ExtraNodeParam.describe()["nodes"]["node_a"]["data1"], 1)
        self.assertEqual(
            ExtraNodeParam.describe()["nodes"]["node_b"]["data3"], {"sample": 1}
        )


class TestParam(TestCase):
    def test_param_extra_info(self):
        """Add extra data to the param"""
        self.assertEqual(ExtraNodeParam.param_a._extras["data1"], 1)
        self.assertEqual(ExtraNodeParam.param_b._extras["data3"], {"sample": 1})

        self.assertEqual(ExtraNodeParam.describe()["params"]["param_a"]["data1"], 1)
        self.assertEqual(
            ExtraNodeParam.describe()["params"]["param_b"]["data3"], {"sample": 1}
        )


class FlowA(Compose):
    x: int
    node_a: Compose

    def run(self):
        return self.x + self.node_a()


class FlowB(Compose):
    x: int
    node_b: Compose

    def run(self):
        return self.x + self.node_b()


class TestCircularFlow:
    def test_recursion_error_while_execute(self):
        """Add extra data to the param"""
        flow_a = FlowA(x=1)
        flow_b = FlowB(x=2, node_b=flow_a)
        flow_b.node_b.node_a = flow_b
        with pytest.raises(RecursionError):
            flow_a()

    def test_rescursion_error_while_dump(self):
        flow_a = FlowA(x=1)
        flow_b = FlowB(x=2, node_b=flow_a)
        flow_b.node_b.node_a = flow_b
        with pytest.raises(RecursionError):
            print(flow_a.dump())
