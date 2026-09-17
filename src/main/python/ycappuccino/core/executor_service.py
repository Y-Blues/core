"""
Utilities to have a callable, runnable and executor like in java in python
"""

from threading import Semaphore, current_thread
from concurrent.futures import Future
from concurrent.futures.thread import ThreadPoolExecutor
import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


class Callable(object):

    def __init__(self, a_name: str, a_log: logging.Logger | None = None) -> None:
        self._name = a_name
        self._log = a_log if a_log is not None else logger

    def run(self) -> Any:
        """main loop for the thread that call the run"""
        pass


class RunnableProcess(Callable):

    def __init__(self, a_name: str, a_log: logging.Logger | None = None) -> None:
        super(RunnableProcess, self).__init__(a_name, a_log)
        self._activate = False
        self._semaphore = Semaphore()

    def process(self) -> None:
        """abstract run class"""
        pass

    def is_active(self) -> bool:
        self._log.info("RunnableProcess {} activate ".format(self._name))
        return self._activate

    def run(self) -> None:
        """main loop for the thread that call the run"""
        try:
            while self._activate:
                self.process()
        except Exception as e:
            self.handle_exception(e)

        self.release_callable()

    def set_activate(self, a_boolean: bool) -> None:
        """start the thread"""
        self._semaphore.acquire()
        logger.info("set_activate {} value {}".format(self._name, a_boolean))
        self._activate = a_boolean
        self._semaphore.release()

    def release_callable(self) -> None:
        """method call when the thread is finish"""
        self._log.info("release RunnableProcess {}  ".format(self._name))

    def handle_exception(self, a_exception: Exception) -> None:
        """method call when a exception in the main loop occured"""
        self._log.error("ERROR RunnableProcess {}  ".format(self._name))
        self._log.exception(a_exception)


def _run(a_runnable: Callable | None) -> Any:
    try:
        if a_runnable != None:
            current_thread().name = a_runnable._name
            return a_runnable.run()
    except Exception as e:
        logger.exception(e)


class ThreadPoolExecutorCallable(object):
    def __init__(self, name: str, a_max_worker: int = 1) -> None:
        self._name = name
        self._executor = ThreadPoolExecutor(max_workers=a_max_worker)

    def submit(self, a_runnable: Callable) -> Future:
        return self._executor.submit(_run, a_runnable)

    def shutdown(self) -> None:
        self._executor.shutdown()


def new_executor(name: str, a_max_worker: int = 1) -> ThreadPoolExecutorCallable:
    return ThreadPoolExecutorCallable(name, a_max_worker)


class ScheduleRunnable(RunnableProcess):
    def __init__(self, a_executor: "SchedulerExecutorCallable", a_timer: float, a_log: logging.Logger | None = None) -> None:
        super(ScheduleRunnable, self).__init__("ScheduleRunnable", a_log)
        self._timer = a_timer
        self._executor = a_executor

    def process(self) -> None:
        """abstract run class"""
        for a_runnable in self._executor.get_runnable():
            a_runnable.run()
        time.sleep(self._timer)


class SchedulerExecutorCallable(object):
    def __init__(self, name: str, a_timer: float) -> None:
        self._name = name
        self._executor = ThreadPoolExecutor(max_workers=1)
        self._runnable: list[Callable] = []
        self._runnable_main = ScheduleRunnable(self, a_timer)
        self._future = None

    def submit(self, a_runnable: Callable) -> Future:
        self._runnable.append(a_runnable)
        if self._future is None:
            self._runnable_main.set_activate(True)
            self._future = self._executor.submit(_run, self._runnable_main)
        return self._future

    def get_runnable(self) -> list[Callable]:
        return self._runnable

    def shutdown(self) -> None:
        self._runnable_main.set_activate(False)
        self._executor.shutdown()


def new_schedule_executor(name: str, a_timer: float) -> SchedulerExecutorCallable:
    return SchedulerExecutorCallable(name, a_timer)
