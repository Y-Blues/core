import logging
import threading
import unittest

import support  # noqa: F401

from ycappuccino.core import executor_service
from ycappuccino.core.executor_service import (
    Callable,
    RunnableProcess,
    new_executor,
    new_schedule_executor,
)


class CountingRunnable(Callable):

    def __init__(self):
        super().__init__("counting")
        self.count = 0

    def run(self):
        self.count += 1


class OneShotProcess(RunnableProcess):

    def __init__(self):
        super().__init__("one-shot")
        self.processed = 0

    def process(self):
        self.processed += 1
        self.set_activate(False)


class TestRunnableProcess(unittest.TestCase):

    def test_uses_the_given_logger(self):
        with self.assertLogs("custom", logging.INFO):
            RunnableProcess("process", logging.getLogger("custom")).is_active()

    def test_defaults_to_the_module_logger(self):
        with self.assertLogs(executor_service.logger, logging.INFO):
            RunnableProcess("process").is_active()

    def test_process_runs_while_active(self):
        process = OneShotProcess()
        process.set_activate(True)
        executor = new_executor("one-shot")

        executor.submit(process).result(timeout=5)
        executor.shutdown()

        self.assertEqual(process.processed, 1)


class TestScheduleExecutor(unittest.TestCase):

    def test_submitted_runnables_run_periodically_until_shutdown(self):
        executor = new_schedule_executor("schedule", 0.01)
        runnable = CountingRunnable()

        executor.submit(runnable)
        self.assertTrue(support.wait_until(lambda: runnable.count >= 2))

        stopper = threading.Thread(target=executor.shutdown, daemon=True)
        stopper.start()
        stopper.join(5)
        self.assertFalse(stopper.is_alive())


if __name__ == "__main__":
    unittest.main()
