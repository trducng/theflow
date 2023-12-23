from unittest import TestCase

from theflow.context import Context


class X:
    def __init__(self):
        self.x = 10


def run(context):
    context.set("a", 1)
    context.set("b", 2)
    context.set("c", 3)
    context.set("d", X())


class TestContext(TestCase):
    def test_thread_safe(self):
        """Test if the memory context is thread safe"""
        import threading

        def run(context):
            context.set("a", 1)
            context.set("b", 2)
            context.set("c", 3)

        context = Context()
        threads = []
        for _ in range(10):
            t = threading.Thread(target=run, args=(context,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        self.assertEqual(context.get("a"), 1)
        self.assertEqual(context.get("b"), 2)
        self.assertEqual(context.get("c"), 3)

        print(context)

    def test_process_safe(self):
        """Test if the memory context is accessible and safe in multi-processing"""
        import multiprocessing

        context = Context()
        processes = []
        for _ in range(10):
            p = multiprocessing.Process(target=run, args=(context,))
            processes.append(p)
            p.start()

        for p in processes:
            p.join()

        self.assertEqual(context.get("a"), 1)
        self.assertEqual(context.get("b"), 2)
        self.assertEqual(context.get("c"), 3)
        self.assertEqual(context.get("d").x, 10)

    def test_get_all(self):
        """Test it's possible to get all values from the context"""
        import multiprocessing

        context = Context()
        processes = []
        for _ in range(10):
            p = multiprocessing.Process(target=run, args=(context,))
            processes.append(p)
            p.start()

        for p in processes:
            p.join()

        retrieved_context = context.get(None)

        self.assertEqual(retrieved_context["a"], 1)
        self.assertEqual(retrieved_context["b"], 2)
        self.assertEqual(retrieved_context["c"], 3)
        self.assertTrue(isinstance(retrieved_context["d"], X))
