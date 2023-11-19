from unittest import TestCase

from theflow.base import Function
from theflow.utils.multiprocess import parallel


class IncrementBy(Function):
    x: int

    def run(self, y):
        return self.x + y


class DecrementBy(Function):
    x: int

    def run(self, y):
        return self.x - y


class MultiplyBy(Function):
    x: int

    def run(self, y):
        return self.x * y


def allow_multiprocessing(kwargs):
    func = kwargs.pop("func")
    return func(**kwargs)


class MultiprocessingWorkFlow(Function):
    increment_by: Function = IncrementBy.withx(x=1)
    decrement_by: Function = DecrementBy.withx(x=1)
    multiply_by: Function = MultiplyBy.withx(x=2)

    def run(self, x, times):
        y = self.decrement_by(x)

        tasks = [{"y": y} for _ in range(times)]
        results = list(parallel(self, "increment_by", tasks, processes=min(times, 2)))

        y = sum(results)
        y = self.multiply_by(y)
        return y


class TestWorkflow(TestCase):
    def test_multiprocessing_output(self):
        flow = MultiprocessingWorkFlow()
        output = flow(1, times=10)
        self.assertEqual(output, 20)

    def test_multiprocessing_context_contains_child_processes(self):
        flow = MultiprocessingWorkFlow()
        output = flow(1, times=10)
        self.assertEqual(output, 20)
        self.assertIn(".increment_by[1]", flow.last_run.logs(name=None))
