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


if __name__ == "__main__":
    unittest.main()
