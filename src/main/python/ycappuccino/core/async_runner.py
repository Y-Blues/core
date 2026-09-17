"""
Runs the coroutines of YCappuccino components (start, stop, bind, ...) from the synchronous
iPOPO callbacks, on an event loop owned by a dedicated thread.

Where no thread can be started (a browser under Pyodide), a coroutine is stepped on the calling thread
instead: it runs to completion synchronously as long as it never waits on a pending future (a start()
setting fields, a sleep(0)), keeping components validated in order; once it does wait, run() returns
None and the rest of it continues as a task of the running event loop (Pyodide's), its errors logged.
A stepped coroutine is not itself a task: asyncio.current_task() and asyncio.timeout() see none.
"""

import asyncio
import inspect
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable, Callable, Coroutine

_logger = logging.getLogger(__name__)


async def _await(awaitable: Awaitable) -> Any:
    return await awaitable


class AsyncRunner(object):
    """event loop running in a background thread, started on first use"""

    def __init__(self, name: str = "ycappuccino-async", thread_factory: Callable = threading.Thread) -> None:
        self._name = name
        self._thread_factory = thread_factory
        self._lock = threading.Lock()
        self._loop = None
        self._thread = None
        self._threads_available = True

    def run(self, result: Any) -> Any:
        """return the result, or wait for it when it is awaitable and return its value"""
        if not inspect.isawaitable(result):
            return result

        if not self._threads_available:
            return _step(_await(result))

        if threading.current_thread() is self._thread:
            # called from a coroutine running on the loop: waiting for the loop would deadlock
            with ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(asyncio.run, _await(result)).result()

        try:
            loop = self._get_loop()
        except RuntimeError:
            _logger.info("no thread can be started: coroutines run on the calling thread")
            self._threads_available = False
            return _step(_await(result))
        return asyncio.run_coroutine_threadsafe(_await(result), loop).result()

    def shutdown(self) -> None:
        with self._lock:
            loop, thread = self._loop, self._thread
            self._loop = self._thread = None

        if loop is not None:
            loop.call_soon_threadsafe(loop.stop)
            thread.join()
            loop.close()

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        with self._lock:
            if self._loop is None:
                loop = asyncio.new_event_loop()
                try:
                    thread = self._thread_factory(target=loop.run_forever, name=self._name, daemon=True)
                    thread.start()
                except RuntimeError:
                    loop.close()
                    raise
                self._loop, self._thread = loop, thread
            return self._loop


def _step(coroutine: Coroutine) -> Any:
    """run the coroutine on this thread until it completes or waits on a pending future"""
    pending = None
    try:
        while pending is None or pending.done():
            pending = coroutine.send(None)
    except StopIteration as stop:
        return stop.value
    asyncio.ensure_future(_resume(coroutine, pending))
    return None


async def _resume(coroutine: Coroutine, pending: Any) -> None:
    try:
        while True:
            if pending is None:
                await asyncio.sleep(0)
            else:
                try:
                    await pending
                except BaseException:
                    pass  # the coroutine reads the outcome of the future itself when resumed
            pending = coroutine.send(None)
    except StopIteration:
        pass
    except Exception:
        _logger.exception("a component coroutine failed after waiting")
