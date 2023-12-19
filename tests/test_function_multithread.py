import threading
import time
from concurrent.futures import ThreadPoolExecutor

from theflow import Function


class FunctionA(Function):
    def run(self, idx: int) -> tuple[int, int]:
        ident = threading.get_ident()
        time.sleep(0.1)
        return (idx, ident)


class FunctionB(Function):
    func: FunctionA = FunctionA.withx()

    def run(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [
                (i, executor.submit(lambda *a, **k: self.func(*a, **k), i))
                for i in range(10)
            ]
            result = [each[1].result() for each in futures]
        return result


def test_multithreading():
    func = FunctionB()
    result = func()
    assert len(result) == 10, "Should have 10 results from 10 tasks"

    firsts = [each[0] for each in result]
    assert firsts == list(range(10)), "Args are passed correctly"

    seconds = [each[1] for each in result]
    assert len(set(seconds)) == 2, "Should have 2 different threads"
