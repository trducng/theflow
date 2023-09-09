from unittest import TestCase
from unittest.mock import patch

from theflow.base import Compose, Node


class Multiply(Compose):
    class Middleware:
        middleware = [
            "theflow.middleware.TrackProgressMiddleware",
            "theflow.middleware.CachingMiddleware",
            "theflow.middleware.SkipComponentMiddleware",
        ]

    a: int

    def run(self, x) -> int:
        return self.a * x


class Sum(Compose):
    a: int
    b = Node(default=Multiply, default_kwargs={"a": 1})

    def run(self, x) -> int:
        return self.a + self.b(x)


class Func(Compose):
    a: int
    func = Node(default=Sum, default_kwargs={"a": 1})

    def run(self, x) -> int:
        return self.a + self.func(x)


class CachingMiddlewareTest(TestCase):
    @patch("tests.test_middleware_cache.Multiply.run", return_value=1)
    def test_cache_in_second_call(self, run):
        f = Func(a=1)
        output = f(1)

        self.assertEqual(output, 3)
        run.assert_called_once()

        output2 = f(1)
        self.assertEqual(output2, 3)
        run.assert_called_once()
