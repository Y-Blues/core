import os
import unittest
from unittest import mock

import support  # noqa: F401

from ycappuccino.core import runner


class TestRunner(unittest.TestCase):

    def run_main(self, *argv):
        framework = mock.Mock()
        with mock.patch.object(runner.Framework, "get_framework", return_value=framework):
            runner.main(list(argv))
        return framework

    def test_defaults_to_the_current_directory(self):
        framework = self.run_main()

        framework.init.assert_called_once_with(os.path.join(".", "conf", "application.yml"))
        framework.start.assert_called_once_with()

    def test_root_and_configuration_paths(self):
        framework = self.run_main("--root_path", "app", "--config_yml_path", "other.yml")

        framework.init.assert_called_once_with(os.path.join("app", "other.yml"))


if __name__ == "__main__":
    unittest.main()
