import os
import subprocess
import sys
import unittest

import support  # noqa: F401

from ycappuccino.core import utils
from ycappuccino.core.decorator_app import App, Layer


@App(name="shop")
@Layer(name="ycappuccino_shop")
class Shop(object):
    pass


class TestDecoratorApp(unittest.TestCase):

    def test_layer_and_app_are_attached_to_the_class(self):
        self.assertEqual(getattr(Shop, utils.LAYER_ATTRIBUTE), "ycappuccino_shop")
        self.assertEqual(getattr(Shop, utils.APP_ATTRIBUTE), "shop")

    def test_layer_and_app_are_registered_by_class_name(self):
        self.assertEqual(utils.map_layer_class["Shop"], "ycappuccino_shop")
        self.assertEqual(utils.map_app_class["Shop"], "shop")

    def test_decorators_do_not_import_the_framework(self):
        code = "import sys, ycappuccino.core.decorator_app; print('ycappuccino.core.framework' in sys.modules)"

        output = subprocess.run(
            [sys.executable, "-c", code],
            env=dict(os.environ, PYTHONPATH=os.pathsep.join(sys.path)),
            capture_output=True,
            text=True,
            check=True,
        ).stdout

        self.assertEqual(output.strip(), "False")


if __name__ == "__main__":
    unittest.main()
