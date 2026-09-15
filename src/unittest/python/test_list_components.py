import asyncio
import unittest
from unittest import mock

import support  # noqa: F401

from ycappuccino.core.bundles.list_components import ListComponent


class Pingable(object):

    def __init__(self, identifier):
        self._identifier = identifier
        self.pings = 0

    def id(self):
        return self._identifier

    def ping(self):
        self.pings += 1


class TestListComponent(unittest.TestCase):

    def setUp(self):
        self.component = ListComponent(mock.Mock())
        self.service = Pingable("svc")
        asyncio.run(self.component.bind(self.service))

    def test_call_invokes_the_method_of_a_bound_component(self):
        self.component.call("svc", "ping")

        self.assertEqual(self.service.pings, 1)

    def test_unbound_component_is_no_longer_called(self):
        asyncio.run(self.component.un_bind(self.service))

        self.component.call("svc", "ping")

        self.assertEqual(self.service.pings, 0)


if __name__ == "__main__":
    unittest.main()
