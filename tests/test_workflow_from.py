import shutil
from pathlib import Path
from unittest import TestCase

from theflow.base import Composable


class IncrementBy(Composable):
    x: int

    def run(self, y):
        return self.x + y


class SequentialPipeline(Composable):
    step1: Composable
    step2: Composable
    step3: Composable

    class Config:
        store_result = ".test_temporary"
        run_id = "test_workflow_from"

    def run(self, y):
        y = self.step1(y)
        y = self.step2(y)
        y = self.step3(y)

        return y


class TestWorkflowFrom(TestCase):
    def tearDown(self):
        shutil.rmtree(".test_temporary", ignore_errors=True)

    def test_workflow_from_sequential(self):
        pipeline = SequentialPipeline(
            step1=IncrementBy(x=1),
            step2=IncrementBy(x=2),
            step3=IncrementBy(x=3),
        )
        output = pipeline(y=10)
        self.assertEqual(output, 16)
        self.assertEqual(pipeline.last_run.output(), 16)
        output = pipeline(
            y=10,
            _ff_from=".step2",
            _ff_from_run=Path(pipeline.config.store_result) / pipeline.last_run.id(),
        )
        self.assertEqual(pipeline.last_run.logs(".step1")["status"], "cached")
        self.assertEqual(pipeline.last_run.logs(".step2")["status"], "rerun")
        self.assertEqual(pipeline.last_run.logs(".step3")["status"], "run")
