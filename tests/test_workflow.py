from unittest import TestCase

from finestflow.workflow import YourFlow


class MultiprocessingWorkFlow(YourFlow):
    def initialize(self):
        self.a = 1
        self.b = 2
        self.c = 3

    def run(self):
        return self.a + self.b + self.c

# class TestWorkflow(TestCase):
#     ...

flow = MultiprocessingWorkFlow()
print(flow.run())