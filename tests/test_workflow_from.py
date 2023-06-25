import shutil
from pathlib import Path
from unittest import TestCase

from finestflow.pipeline import Pipeline


class IncrementBy:
    def __init__(self, x):
        self.x = x

    def __call__(self, y):
        return self.x + y


class SequentialPipeline(Pipeline):
    class Config:
        store_result = ".test_temporary"
        run_id = "test_workflow_from"

    def initialize(self):
        self.step1 = IncrementBy(x=1)
        self.step2 = IncrementBy(x=2)
        self.step3 = IncrementBy(x=3)

    def run(self, y):
        y = self.step1(y, _ff_name="step1")
        y = self.step2(y, _ff_name="step2")
        y = self.step3(y, _ff_name="step3")

        return y


class TestWorkflowFrom(TestCase):
    def tearDown(self):
        shutil.rmtree(".test_temporary", ignore_errors=True)

    def test_workflow_from_sequential(self):
        pipeline = SequentialPipeline()
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
