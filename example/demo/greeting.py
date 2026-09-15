"""
Demo components: a greeter service and a component that uses it when the application starts.
"""

import logging
from abc import ABC

from ycappuccino.api.core import IActivityLogger
from ycappuccino.api.core_base import YCappuccinoComponent, YCappuccinoType

_logger = logging.getLogger(__name__)


class IGreeter(YCappuccinoComponent, ABC):
    """interface of the greeter service"""

    def greet(self, name: str) -> str:
        raise NotImplementedError


class Greeter(IGreeter):
    """greets with the greeting configured in application.yml"""

    def __init__(self, greeting: str = "Hello"):
        self._greeting = greeting

    def greet(self, name: str) -> str:
        return f"{self._greeting} {name}!"

    async def start(self):
        pass

    async def stop(self):
        pass


class Welcome(YCappuccinoComponent):
    """logs a greeting once its dependencies are available"""

    def __init__(
        self,
        greeter: IGreeter,
        logger: YCappuccinoType(IActivityLogger, "(name=main)"),
    ):
        self._greeter = greeter
        self._logger = logger

    async def start(self):
        message = self._greeter.greet("YCappuccino")
        _logger.info(message)
        self._logger.info(message)

    async def stop(self):
        self._logger.info("bye")
