from unittest import TestCase
from unittest.mock import patch

import pytest

from theflow import Function, Node

from .assets.sample_flow import Func, Sum1


class MiddleFunction(Function):
    class Config:
        middleware_section = "middleware-test"
        middleware_switches = {
            "theflow.middleware.TrackProgressMiddleware": True,
            "theflow.middleware.SkipComponentMiddleware": True,
            "theflow.middleware.CachingMiddleware": False,
        }

    def run(self):
        ...


@patch("theflow.middleware.TrackProgressMiddleware.__init__", return_value=None)
def test_middleware_init_called(init, set_theflow_settings_module):
    _ = MiddleFunction()
    init.assert_called()


@patch("theflow.middleware.CachingMiddleware.__init__", return_value=None)
def test_middleware_init_switched_off(init, set_theflow_settings_module):
    _ = MiddleFunction()
    init.assert_not_called()


@patch("theflow.middleware.SkipComponentMiddleware.__init__", return_value=None)
def test_middleware_init_not_in_test(init, set_theflow_settings_module):
    _ = MiddleFunction()
    init.assert_not_called()


class CachingMiddlewareTest(TestCase):
    @patch("tests.assets.sample_flow.Multiply.run", return_value=1)
    def test_cache_in_second_call(self, run):
        """The second call shouldn't be run"""
        f = Func(a=1, x=Sum1(a=1))
        output = f(1, 2)

        self.assertEqual(output, 243)
        run.assert_called_once()

        output2 = f(1, 2)
        self.assertEqual(output2, 243)
        run.assert_called_once()  # the last time isn't called, still called once


class A1(Function):
    x: int = 1
    y: Function = Node(default_callback=lambda _: A2(x=1))

    def run(self):
        return self.x + self.y()


class A2(Function):
    x: int = 1

    def run(self):
        return self.x / 0


def test_log_error():
    f = A1(x=10, y=A2())
    with pytest.raises(ZeroDivisionError):
        f()
    assert "error" in f.last_run.logs(".")
    assert f.last_run.logs(".")["error"] == "division by zero"
