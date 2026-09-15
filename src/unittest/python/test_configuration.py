import os
import shutil
import tempfile
import unittest

import support  # noqa: F401

from ycappuccino.core.bundles.configuration import Configuration


class TestConfiguration(unittest.TestCase):

    def setUp(self):
        self.root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.root, True)
        self.addCleanup(os.chdir, os.getcwd())
        os.chdir(self.root)
        os.makedirs("conf")
        with open(os.path.join("conf", "config.properties"), "w") as properties:
            properties.write("# comment\nname = demo\nenabled=true\ndisabled=false\nurl=http://host/?a=b\n")

    def test_reads_the_properties_file_of_the_application(self):
        configuration = Configuration()

        self.assertEqual(configuration.get("name"), "demo")
        self.assertEqual(configuration.get("url"), "http://host/?a=b")
        self.assertTrue(configuration.has("name"))
        self.assertFalse(configuration.has("comment"))

    def test_booleans_are_converted(self):
        configuration = Configuration()

        self.assertIs(configuration.get("enabled"), True)
        self.assertIs(configuration.get("disabled"), False)

    def test_missing_key_returns_the_default(self):
        self.assertEqual(Configuration().get("missing", "fallback"), "fallback")

    def test_set_persists_the_value(self):
        Configuration().set("theme", "dark")

        self.assertEqual(Configuration().get("theme"), "dark")

    def test_keys_cannot_contain_an_equal_sign(self):
        with self.assertRaises(KeyError):
            Configuration().set("a=b", "c")

    def test_file_name_can_be_changed(self):
        with open(os.path.join("conf", "other.properties"), "w") as properties:
            properties.write("x=1\n")

        self.assertEqual(Configuration("other.properties").get("x"), "1")


if __name__ == "__main__":
    unittest.main()
