import asyncio
import threading
import unittest

import support  # noqa: F401

from ycappuccino.core.async_runner import AsyncRunner


class TestAsyncRunner(unittest.TestCase):

    def setUp(self):
        self.runner = AsyncRunner()
        self.addCleanup(self.runner.shutdown)

    def test_plain_values_are_returned_as_is(self):
        self.assertEqual(self.runner.run(42), 42)

    def test_coroutines_are_awaited_on_a_dedicated_thread(self):
        async def current_thread_name():
            await asyncio.sleep(0)
            return threading.current_thread().name

        self.assertNotEqual(self.runner.run(current_thread_name()), threading.current_thread().name)

    def test_exceptions_are_propagated(self):
        async def fail():
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            self.runner.run(fail())

    def test_nested_runs_do_not_deadlock(self):
        async def inner():
            return "inner"

        async def outer():
            return self.runner.run(inner())

        result = {}
        worker = threading.Thread(
            target=lambda: result.update(value=self.runner.run(outer())), daemon=True
        )
        worker.start()
        worker.join(5)

        self.assertEqual(result.get("value"), "inner")

    def test_runner_is_usable_after_shutdown(self):
        async def value():
            return 1

        self.runner.run(value())
        self.runner.shutdown()

        self.assertEqual(self.runner.run(value()), 1)



def _no_thread(*args, **kwargs):
    raise RuntimeError("can't start new thread")


class TestAsyncRunnerWithoutThreads(unittest.TestCase):
    """a browser under Pyodide: no OS thread can be started"""

    def setUp(self):
        self.runner = AsyncRunner(thread_factory=_no_thread)
        self.addCleanup(self.runner.shutdown)

    def test_a_coroutine_that_never_really_waits_runs_to_completion_on_the_calling_thread(self):
        async def current_thread_name():
            await asyncio.sleep(0)
            return threading.current_thread().name

        self.assertEqual(self.runner.run(current_thread_name()), threading.current_thread().name)

    def test_exceptions_are_propagated(self):
        async def fail():
            raise ValueError("boom")

        with self.assertRaises(ValueError):
            self.runner.run(fail())

    def test_nested_runs_complete(self):
        async def inner():
            return "inner"

        async def outer():
            return self.runner.run(inner())

        self.assertEqual(self.runner.run(outer()), "inner")

    def test_a_coroutine_suspended_on_a_pending_future_finishes_on_the_running_loop(self):
        steps = []

        async def scenario():
            future = asyncio.get_running_loop().create_future()

            async def start():
                steps.append("before")
                steps.append(await future)

            self.assertIsNone(self.runner.run(start()))
            self.assertEqual(steps, ["before"])
            future.set_result("after")
            for _ in range(3):
                await asyncio.sleep(0)

        asyncio.run(scenario())

        self.assertEqual(steps, ["before", "after"])

    def test_an_error_after_the_suspension_is_logged(self):
        async def scenario():
            future = asyncio.get_running_loop().create_future()

            async def start():
                await future
                raise ValueError("late")

            self.runner.run(start())
            future.set_result(None)
            for _ in range(3):
                await asyncio.sleep(0)

        with self.assertLogs("ycappuccino.core.async_runner", "ERROR"):
            asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
