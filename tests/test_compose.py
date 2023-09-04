from unittest import TestCase

from theflow import Compose, Node, Param, load


def callback(obj, type_):
    return obj.a * 2


class Sum1(Compose):
    a: int
    b: int = 10
    c: int = 10
    d: Param[int] = Param(depends_on="b", default_callback=lambda obj, type_: obj.b * 2)

    def run(self) -> int:
        return self.a + self.b + self.c


class Sum2(Compose):
    a: int

    def run(self, a, b: int, *args, **kwargs) -> int:
        return self.a + a + b


class Plus(Compose):
    a: int
    e: int
    x: Compose
    y = Node(default=Sum1, default_kwargs={"a": 100})
    m = Node(default=Sum2, default_kwargs={"a": 100})

    @Param.decorate()
    def f(self):
        return self.a + self.e

    @Node.decorate(depends_on="x")
    def z(self):
        return Sum1(a=self.x.a * 10)

    def run(self) -> int:
        x, y, m = self.x(), self.y(), self.m()
        return x + y + m


class TestComposeSaveAndLoad(TestCase):
    def test_save_ignore_depend_as_default(self):
        """By default, ignore_depends for the output"""
        obj = Plus(a=20, e=20, x=Sum1(a=20))
        d = obj.dump()
        self.assertEqual(
            d,
            {
                "type": "tests.test_compose.Plus",
                "params": {"a": 20, "e": 20, "f": 40},
                "nodes": {
                    "m": {
                        "type": "tests.test_compose.Sum2",
                        "params": {"a": 100},
                        "nodes": {},
                    },
                    "x": {
                        "type": "tests.test_compose.Sum1",
                        "params": {"a": 20, "b": 10, "c": 10},
                        "nodes": {},
                    },
                    "y": {
                        "type": "tests.test_compose.Sum1",
                        "params": {"a": 100, "b": 10, "c": 10},
                        "nodes": {},
                    },
                },
            },
        )

    def test_save_no_ignore_depends(self):
        """Include params and nodes with ignore_depends"""
        obj = Plus(a=20, e=20, x=Sum1(a=20))
        d = obj.dump(ignore_depends=False)
        self.assertEqual(
            d,
            {
                "type": "tests.test_compose.Plus",
                "params": {"a": 20, "e": 20, "f": 40},
                "nodes": {
                    "m": {
                        "type": "tests.test_compose.Sum2",
                        "params": {"a": 100},
                        "nodes": {},
                    },
                    "x": {
                        "type": "tests.test_compose.Sum1",
                        "params": {"a": 20, "b": 10, "c": 10, "d": 20},
                        "nodes": {},
                    },
                    "y": {
                        "type": "tests.test_compose.Sum1",
                        "params": {"a": 100, "b": 10, "c": 10, "d": 20},
                        "nodes": {},
                    },
                    "z": {
                        "type": "tests.test_compose.Sum1",
                        "params": {"a": 200, "b": 10, "c": 10, "d": 20},
                        "nodes": {},
                    },
                },
            },
        )

    def test_load_successfully_unsafe(self):
        """By default, ignore_depends for the output"""
        obj = Plus(a=20, e=20, x=Sum1(a=20))
        d = obj.dump()
        obj2 = load(d, safe=False)
        self.assertEqual(obj.dump(), obj2.dump())

    def test_load_safe_without_module_raise_error(self):
        """Raise error if without supplied modules"""
        obj = Plus(a=20, e=20, x=Sum1(a=20))
        d = obj.dump()
        with self.assertRaises(ValueError):
            load(d)

    def test_load_safe_missing_module_raise_error(self):
        """Raise error if without supplied modules"""
        obj = Plus(a=20, e=20, x=Sum1(a=20))
        d = obj.dump()
        with self.assertRaises(ValueError):
            load(d, allowed_modules={"tests.test_compose.Plus": Plus})

    def test_load_safe_with_module(self):
        """Raise error if without supplied modules"""
        obj = Plus(a=20, e=20, x=Sum1(a=20))
        d = obj.dump()
        obj2 = load(
            d,
            allowed_modules={
                "tests.test_compose.Sum1": Sum1,
                "tests.test_compose.Sum2": Sum2,
                "tests.test_compose.callback": callback,
                "tests.test_compose.Plus": Plus,
            },
        )
        self.assertEqual(obj.dump(), obj2.dump())

    def test_persist_flow(self):
        """Represent flow in a serialiable way that can be init later"""
        obj = Plus(a=20, e=20, x=Sum1(a=20))
        persisted = obj.__persist_flow__()
        self.assertEqual(
            persisted,
            {
                "__type__": "tests.test_compose.Plus",
                "a": 20,
                "e": 20,
                "f": 40,
                "m": {"__type__": "tests.test_compose.Sum2", "a": 100},
                "x": {"__type__": "tests.test_compose.Sum1", "a": 20, "b": 10, "c": 10},
                "y": {
                    "__type__": "tests.test_compose.Sum1",
                    "a": 100,
                    "b": 10,
                    "c": 10,
                },
            },
        )
