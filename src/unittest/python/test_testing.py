import os
import unittest

import support  # noqa: F401

from ycappuccino.core.testing import TemporaryApplication, read_file, wait_until


class TestTemporaryApplication(unittest.TestCase):

    def test_files_are_written_with_a_unique_package_name(self):
        app = TemporaryApplication(
            {"PACKAGE/__init__.py": "", "conf/application.yml": "bundle_prefix: PACKAGE\n"}
        ).open()
        self.addCleanup(app.close)

        self.assertEqual(os.getcwd(), app.root)
        self.assertTrue(os.path.isfile(os.path.join(app.root, app.package, "__init__.py")))
        self.assertEqual(read_file(app.yml_path), f"bundle_prefix: {app.package}\n")

    def test_close_restores_the_directory_and_removes_the_files(self):
        previous_cwd = os.getcwd()
        app = TemporaryApplication({"PACKAGE/__init__.py": ""}).open()

        app.close()

        self.assertEqual(os.getcwd(), previous_cwd)
        self.assertFalse(os.path.exists(app.root))

    def test_close_without_open_only_removes_the_files(self):
        app = TemporaryApplication({"PACKAGE/__init__.py": ""})

        app.close()

        self.assertFalse(os.path.exists(app.root))


class TestHelpers(unittest.TestCase):

    def test_wait_until_returns_the_first_truthy_value(self):
        values = iter([None, 0, "done"])

        self.assertEqual(wait_until(lambda: next(values), timeout=1), "done")

    def test_read_file_of_a_missing_file_is_empty(self):
        self.assertEqual(read_file("/nonexistent/ycappuccino/file"), "")


if __name__ == "__main__":
    unittest.main()
