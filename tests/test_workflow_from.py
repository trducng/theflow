import shutil
from unittest import TestCase

from theflow.base import Compose
from theflow.storage import storage


class IncrementBy(Compose):
    x: int

    def run(self, y):
        return self.x + y


class SequentialPipeline(Compose):
    step1: Compose
    step2: Compose
    step3: Compose

    class Config:
        store_result = ".test_temporary"

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

        pipeline2 = SequentialPipeline(
            step1=IncrementBy(x=1),
            step2=IncrementBy(x=2),
            step3=IncrementBy(x=3),
        )
        output = pipeline2(
            y=10,
            _ff_from=".step2",
            _ff_from_run=storage.url(
                pipeline2.config.store_result, pipeline.last_run.id()
            ),
        )
        self.assertEqual(pipeline2.last_run.logs(".step1")["status"], "cached")
        self.assertEqual(pipeline2.last_run.logs(".step2")["status"], "run")
        self.assertEqual(pipeline2.last_run.logs(".step3")["status"], "run")
