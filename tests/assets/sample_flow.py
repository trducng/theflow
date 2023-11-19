from theflow import Function, Node, Param, unset


def callback(obj):
    return obj.a * 2


class Multiply(Function):
    a: int

    def run(self, x) -> int:
        return self.a * x


class Sum1(Function):
    a: int = Param(unset)
    b: int = 10
    c: int = 10
    d: int = Param(
        default=unset, depends_on="b", auto_callback=lambda obj: obj.b * 2, cache=True
    )

    def run(self) -> int:
        return self.a + self.b + self.c


class Sum2(Function):
    a: int
    mult: Function = Multiply.withx(a=10)

    def run(self, a, b: int, *args, **kwargs) -> int:
        return self.a + a + self.mult(b)


class Func(Function):
    """Function calculation"""

    class Config:
        middleware_switches = {"theflow.middleware.CachingMiddleware": True}

    a: int = Param(default=100, help="The `a` number")
    e: int = Param(default=unset, help="The `e` number")
    x: Sum1
    y: Function = Node(default=Sum1.withx(a=100), help="The `y` node")
    m: Function = Node(default=Sum2.withx(a=100))

    @Param.auto()
    def f(self):
        return self.a + self.e

    @Node.auto(depends_on="x")
    def z(self):
        return Sum1(a=self.x.a * 10)

    def run(self, ma, mb) -> int:
        x, y, m = self.x(), self.y(), self.m(ma, mb)
        return x + y + m
