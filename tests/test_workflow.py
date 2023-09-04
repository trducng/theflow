import multiprocessing
from unittest import TestCase

import pytest

from theflow.base import Composable, Node


class IncrementBy(Composable):
    x: int

    def run(self, y):
        return self.x + y


class DecrementBy(Composable):
    x: int

    def run(self, y):
        return self.x - y


class MultiplyBy(Composable):
    x: int

    def run(self, y):
        return self.x * y


def allow_multiprocessing(kwargs):
    func = kwargs.pop("func")
    return func(**kwargs)


class MultiprocessingWorkFlow(Composable):
    increment_by = Node(default=IncrementBy, default_kwargs={"x": 1})
    decrement_by = Node(default=DecrementBy, default_kwargs={"x": 1})
    multiply_by = Node(default=MultiplyBy, default_kwargs={"x": 2})

    def run(self, x, times):
        y = self.decrement_by(x)

        tasks = [{"y": y, "func": self.increment_by} for _ in range(times)]
        with multiprocessing.Pool(processes=min(times, 2)) as pool:
            results = [each for each in pool.imap(allow_multiprocessing, tasks)]

        y = sum(results)
        y = self.multiply_by(y)
        return y


class TestWorkflow(TestCase):
    def test_multiprocessing_output(self):
        flow = MultiprocessingWorkFlow()
        output = flow(1, times=10)
        self.assertEqual(output, 20)

    @pytest.mark.skip(reason="theflow hasn't fully supported multiprocessing")
    def test_multiprocessing_context_contains_child_processes(self):
        flow = MultiprocessingWorkFlow()
        flow.context.activate_multiprocessing()
        output = flow(1, times=10)
        flow.context.deactivate_multiprocessing()
        self.assertEqual(output, 20)
        self.assertIn(".increment[1]", flow.last_run.logs(name=None))

    def test_multiprocessing_context_doesnt_contain_child_processes_not_activated(self):
        flow = MultiprocessingWorkFlow()
        output = flow(1, times=10)
        self.assertEqual(output, 20)
        self.assertNotIn(".increment[1]", flow.last_run.logs(name=None))
