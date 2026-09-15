import os
import shutil
import tempfile
import unittest

import support  # noqa: F401

from ycappuccino.core.bundles.activity_logger import ActivityLogger


class DictConfiguration(object):

    def __init__(self, values=None):
        self._values = values or {}

    def get(self, key, default=None):
        return self._values.get(key, default)


class TestActivityLogger(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.root)

    def create(self, values=None, name="main"):
        logger = ActivityLogger(DictConfiguration(values), name)
        self.addCleanup(lambda: [handler.close() for handler in logger.handlers])
        return logger

    def read(self, file_name):
        return support.read_file(os.path.join(self.root, "data", "log", file_name))

    def test_writes_in_a_file_named_after_the_logger(self):
        self.create().info("hello")

        self.assertIn("hello", self.read("Log-Activity-main.log"))

    def test_file_and_level_come_from_configuration(self):
        logger = self.create(
            {"activity.logger.audit.file": "audit.log", "activity.logger.audit.level": "ERROR"},
            name="audit",
        )

        logger.info("ignored")
        logger.error("kept")

        self.assertIn("kept", self.read("audit.log"))
        self.assertNotIn("ignored", self.read("audit.log"))

    def test_default_logger_uses_unprefixed_configuration(self):
        self.create({"activity.logger.file": "default.log"}, name="default").warning("careful")

        self.assertIn("careful", self.read("default.log"))


if __name__ == "__main__":
    unittest.main()
