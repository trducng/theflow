from theflow import Compose, Node, Param


def callback(obj, type_):
    return obj.a * 2


class Multiply(Compose):
    a: int

    def run(self, x) -> int:
        return self.a * x


class Sum1(Compose):
    a: int
    b: int = 10
    c: int = 10
    d: Param[int] = Param(depends_on="b", default_callback=lambda obj, type_: obj.b * 2)

    def run(self) -> int:
        return self.a + self.b + self.c


class Sum2(Compose):
    a: int
    mult: Node[Compose] = Node(default=Multiply, default_kwargs={"a": 10})

    def run(self, a, b: int, *args, **kwargs) -> int:
        return self.a + a + self.mult(b)


class Func(Compose):
    """Function calculation"""

    class Config:
        middleware_switches = {"theflow.middleware.CachingMiddleware": True}

    a: Param[int] = Param(default=100, help="The `a` number")
    e: Param[int] = Param(help="The `e` number")
    x: Compose
    y = Node(default=Sum1, default_kwargs={"a": 100}, help="The `y` node")
    m = Node(default=Sum2, default_kwargs={"a": 100})

    @Param.decorate()
    def f(self):
        return self.a + self.e

    @Node.decorate(depends_on="x")
    def z(self):
        return Sum1(a=self.x.a * 10)

    def run(self, ma, mb) -> int:
        x, y, m = self.x(), self.y(), self.m(ma, mb)
        return x + y + m
