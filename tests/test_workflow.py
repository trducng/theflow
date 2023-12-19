from unittest import TestCase

from theflow.base import ConcurrentFunction, Function, SequentialFunction
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


def test_creating_sequential_function():
    flow = IncrementBy(x=10) >> DecrementBy(x=20) >> MultiplyBy(x=3)

    assert len(flow.funcs) == 3, "Should have 3 functions"
    assert len(flow) == 3, "Should have 3 functions"
    assert flow[0].x == 10, "Should have the first function as IncrementBy with x=10"
    assert flow(1) == 27, "(20 - (10 + 1)) * 3"
    assert flow.last_run.logs(".func1_DecrementBy")["output"] == 9


def test_creating_concurrent_function():
    flow = IncrementBy(x=10) // DecrementBy(x=20) // MultiplyBy(x=3)

    assert len(flow.funcs) == 3, "Should have 3 functions"
    assert len(flow) == 3, "Should have 3 functions"
    assert flow[0].x == 10, "Should have the first function as IncrementBy with x=10"
    assert flow(1) == [11, 19, 3], "Should have the output of each function"
    assert flow.last_run.logs(".func1_DecrementBy")["output"] == 19


def test_mixed_sequential_concurrent_function():
    flow = (IncrementBy(x=10) >> DecrementBy(x=20)) // MultiplyBy(x=3)

    assert isinstance(flow, ConcurrentFunction), "Should be a ConcurrentFunction"
    assert len(flow.funcs) == 2, "Should have 2 functions"
    assert len(flow) == 2, "Should have 2 functions"
    assert isinstance(flow[0], SequentialFunction), "Should be a SequentialFunction"
    assert isinstance(flow[1], MultiplyBy), "Should be a MultipleBy"
    assert flow(1) == [9, 3], "Should have the output of each function"
    assert flow.last_run.logs(".func0_SequentialFunction")["output"] == 9


def test_mixed_sequential_concurrent_function_complex():
    flow = (IncrementBy(x=10) >> DecrementBy(x=20)) // (
        MultiplyBy(x=3) >> IncrementBy(x=10) >> DecrementBy(x=20)
    )

    assert isinstance(flow, ConcurrentFunction), "Should be a ConcurrentFunction"
    assert len(flow.funcs) == 2, "Should have 2 functions"
    assert len(flow) == 2, "Should have 2 functions"
    assert isinstance(flow[0], SequentialFunction), "Should be a SequentialFunction"
    assert isinstance(flow[1], SequentialFunction), "Should be a SequentialFunction"
    assert flow(1) == [9, 7], "Should have the output of each function"
    assert flow.last_run.logs(".func0_SequentialFunction")["output"] == 9
    assert (
        flow.last_run.logs(".func1_SequentialFunction.func1_IncrementBy")["output"]
        == 13
    )


class FunctionA(Function):
    def run(self, x):
        return x + 1


class FunctionB(Function):
    seq: FunctionA = FunctionA.withx() >> FunctionA.withx()
    con: FunctionA = FunctionA.withx() // FunctionA.withx()

    def run(self, x):
        return self.seq(x) + sum(self.con(x)) + 1


def test_valid_default_sequential_and_concurrent_function():
    flow = FunctionB()
    assert flow(1) == 8, "Should initiate default sequential and concurrent function"


class DuplicateNodeCall(Function):
    increment_by: Function = IncrementBy.withx(x=1)

    def run(self, x):
        result = -1
        if isinstance(self.increment_by, IncrementBy):
            result = self.increment_by(y=x)

        return result


class NonDuplicateNodeCall(Function):
    increment_by: Function = IncrementBy.withx(x=1)

    def run(self, x):
        result = -1
        if isinstance(self.get_from_path("increment_by"), IncrementBy):
            result = self.increment_by(y=x)

        return result


def test_duplicate_node_call():
    """Undesired logs"""
    flow = DuplicateNodeCall()
    output = flow(1)
    assert output == -1, "The isinstance check should fail"
    assert ".increment_by" not in flow.last_run.logs()
    assert ".increment_by[1]" not in flow.last_run.logs()


def test_non_duplicate_node_call():
    """Desired logs"""
    flow = NonDuplicateNodeCall()
    output = flow(1)
    assert output == 2, "Should have incremented by 1"
    assert ".increment_by" in flow.last_run.logs()
    assert ".increment_by[1]" not in flow.last_run.logs()
