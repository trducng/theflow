import multiprocessing
from unittest import TestCase

from finestflow.pipeline import Pipeline


class IncrementBy:
    def __init__(self, x):
        self.x = x

    def run(self, y):
        return self.x + y

class DecrementBy:
    def __init__(self, x):
        self.x = x

    def run(self, y):
        return self.x - y


class MultiplyBy:
    def __init__(self, x):
        self.x = x

    def run(self, y):
        return self.x * y

def allow_multiprocessing(kwargs):
    func = kwargs.pop("func")
    return func.run(**kwargs)

class MultiprocessingWorkFlow(Pipeline):
    def initialize(self):
        self.increment_by = IncrementBy(1)
        self.decrement_by = DecrementBy(1)
        self.multiply_by = MultiplyBy(2)

    def run(self, x, times):
        y = self.decrement_by.run(x, _ff_name="decrement")

        with multiprocessing.Pool(processes=min(times, 2)) as pool:
            results = [each for each in pool.imap(
                allow_multiprocessing,
                [{"y": y, "_ff_name": f"increment_{idx}", "func": self.increment_by} for idx in range(times)]
            )]

        y = sum(results)
        y = self.multiply_by.run(y, _ff_name="multiply")
        return y

class TestWorkflow(TestCase):
    def test_multiprocessing_output(self):
        flow = MultiprocessingWorkFlow()
        output = flow.run(1, times=10)
        self.assertEqual(output, 20)

    def test_multiprocessing_context_contains_child_processes(self):
        flow = MultiprocessingWorkFlow()
        flow._ff_run_context.activate_multiprocessing()
        output = flow.run(1, times=10)
        flow._ff_run_context.deactivate_multiprocessing()
        self.assertEqual(output, 20)
        self.assertIn(".increment_1", flow._ff_run_context.get(name=None))

    def test_multiprocessing_context_doesnt_contain_child_processes_not_activated(self):
        flow = MultiprocessingWorkFlow()
        output = flow.run(1, times=10)
        self.assertEqual(output, 20)
        self.assertNotIn(".increment_1", flow._ff_run_context.get(name=None))
