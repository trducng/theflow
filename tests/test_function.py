from copy import deepcopy
from unittest import TestCase

import pytest

from theflow import Function, Node, Param, load
from theflow.config import DefaultConfig
from theflow.debug import likely_cyclic_pipeline
from theflow.exceptions import CyclicPipelineError

from .assets.sample_flow import Func, Multiply, Sum1, Sum2, callback


class TestFunctionSaveAndLoad(TestCase):
    def test_save_ignore_auto_as_default(self):
        """By default, ignore_auto for the output"""
        obj = Func(a=20, e=20, x=Sum1(a=20))
        obj_def = obj.dump()

        # config-related result
        default_config = {
            k: v for k, v in DefaultConfig.__dict__.items() if not k.startswith("_")
        }
        func_config = deepcopy(default_config)
        func_config["middleware_switches"][
            "theflow.middleware.CachingMiddleware"
        ] = True

        self.assertDictEqual(
            obj_def,
            {
                "function": "tests.assets.sample_flow.Func",
                "params": {"a": 20, "e": 20},
                "nodes": {
                    "m": {
                        "function": "tests.assets.sample_flow.Sum2",
                        "params": {"a": 100},
                        "nodes": {
                            "mult": {
                                "function": "tests.assets.sample_flow.Multiply",
                                "params": {"a": 10},
                                "nodes": {},
                                "configs": default_config,
                            },
                        },
                        "configs": default_config,
                    },
                    "x": {
                        "function": "tests.assets.sample_flow.Sum1",
                        "params": {"a": 20, "b": 10, "c": 10},
                        "nodes": {},
                        "configs": default_config,
                    },
                    "y": {
                        "function": "tests.assets.sample_flow.Sum1",
                        "params": {"a": 100, "b": 10, "c": 10},
                        "nodes": {},
                        "configs": default_config,
                    },
                },
                "configs": func_config,
            },
        )

    def test_save_no_ignore_auto(self):
        """Include params and nodes with ignore_auto"""
        obj = Func(a=20, e=20, x=Sum1(a=20))
        obj_def = obj.dump(ignore_auto=False)

        # config-related result
        default_config = {
            k: v for k, v in DefaultConfig.__dict__.items() if not k.startswith("_")
        }
        func_config = deepcopy(default_config)
        func_config["middleware_switches"][
            "theflow.middleware.CachingMiddleware"
        ] = True

        self.assertDictEqual(
            obj_def,
            {
                "function": "tests.assets.sample_flow.Func",
                "params": {"a": 20, "e": 20, "f": 40},
                "nodes": {
                    "m": {
                        "function": "tests.assets.sample_flow.Sum2",
                        "params": {"a": 100},
                        "nodes": {
                            "mult": {
                                "function": "tests.assets.sample_flow.Multiply",
                                "params": {"a": 10},
                                "nodes": {},
                                "configs": default_config,
                            },
                        },
                        "configs": default_config,
                    },
                    "x": {
                        "function": "tests.assets.sample_flow.Sum1",
                        "params": {"a": 20, "b": 10, "c": 10, "d": 20},
                        "nodes": {},
                        "configs": default_config,
                    },
                    "y": {
                        "function": "tests.assets.sample_flow.Sum1",
                        "params": {"a": 100, "b": 10, "c": 10, "d": 20},
                        "nodes": {},
                        "configs": default_config,
                    },
                    "z": {
                        "function": "tests.assets.sample_flow.Sum1",
                        "params": {"a": 200, "b": 10, "c": 10, "d": 20},
                        "nodes": {},
                        "configs": default_config,
                    },
                },
                "configs": func_config,
            },
        )

    def test_load_successfully_unsafe(self):
        """By default, ignore_auto for the output"""
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


class ExtraNodeParam(Function):
    param_a: str = Param(help="Param A", data1=1, data2="2")
    node_a: Function = Node(help="Node A", data1=1, data2="2")
    node_b: Function = Node(default_callback=lambda _: Function(), data3={"sample": 1})

    @Param.auto(data3={"sample": 1}, depends_on=["node_a"])
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


class A(Function):
    x: int = 1
    y1: Function

    def run(self, a):
        return self.x + self.y1(a)


class B(Function):
    x: int = 1
    y2: Function

    def run(self, a):
        return self.x + self.y2(a)


class C(Function):
    x: int = 1
    y3: Function

    def run(self, a):
        return self.x + self.y3(a)


class A1(Function):
    x: int = 1
    y: Function = Node(default_callback=lambda _: A2(x=1))

    def run(self):
        return self.x + self.y()


class A2(Function):
    x: int = 1
    y: Function = Node(default_callback=lambda _: A1(x=1))

    def run(self):
        return self.x + self.y()


class B2(Function):
    x: int = 1

    def run(self):
        return self.x


class TestCircularDependency:
    """Check for analyzing circular dependency"""

    def test_execute_circular_dependency_raise_error(self):
        """Prove that the circular dependency is detected at runtime"""
        a = A()
        b = B()
        c = C()
        a.y1 = b
        b.y2 = c
        c.y3 = a
        with pytest.raises(CyclicPipelineError):
            a(12)

    def test_dumping_circular_dependency_raise_error(self):
        """Prove that the circular dependency is detected at runtime"""
        a = A()
        b = B()
        c = C()
        a.y1 = b
        b.y2 = c
        c.y3 = a
        with pytest.raises(RecursionError):
            a.dump()

    def test_initiating_circular_dependency_doesnt_raise_error(self):
        assert isinstance(A1(), A1)

    def test_detect_circular_dependency_positive(self):
        """Detect circular dependency during analysis"""
        a = A()
        b = B()
        c = C()
        a.y1 = b
        b.y2 = c
        c.y3 = a
        assert likely_cyclic_pipeline(a)[0]
        assert likely_cyclic_pipeline(b)[0]
        assert likely_cyclic_pipeline(c)[0]

    def test_detect_simple_circular_dependency_positive(self):
        """Prove that the circular dependency is detected at runtime"""
        a = A1()
        assert likely_cyclic_pipeline(a)[0]

    def test_detect_circular_dependency_negative(self):
        """Detect circular dependency during analysis"""
        a = A1()
        b = A2()
        c = B2()
        a.y = b
        b.y = c
        assert not likely_cyclic_pipeline(a)[0]
        assert not likely_cyclic_pipeline(b)[0]
        assert not likely_cyclic_pipeline(c)[0]
