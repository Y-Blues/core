"""
Runs the coroutines of YCappuccino components (start, stop, bind, ...) from the synchronous
iPOPO callbacks, on an event loop owned by a dedicated thread.
"""

import asyncio
import inspect
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Awaitable


async def _await(awaitable: Awaitable) -> Any:
    return await awaitable


class AsyncRunner(object):
    """event loop running in a background thread, started on first use"""

    def __init__(self, name: str = "ycappuccino-async") -> None:
        self._name = name
        self._lock = threading.Lock()
        self._loop = None
        self._thread = None

    def run(self, result: Any) -> Any:
        """return the result, or wait for it when it is awaitable and return its value"""
        if not inspect.isawaitable(result):
            return result

        if threading.current_thread() is self._thread:
            # called from a coroutine running on the loop: waiting for the loop would deadlock
            with ThreadPoolExecutor(max_workers=1) as executor:
                return executor.submit(asyncio.run, _await(result)).result()

        return asyncio.run_coroutine_threadsafe(_await(result), self._get_loop()).result()

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
                self._loop = asyncio.new_event_loop()
                self._thread = threading.Thread(
                    target=self._loop.run_forever, name=self._name, daemon=True
                )
                self._thread.start()
            return self._loop
