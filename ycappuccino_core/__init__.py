# YCappuccino ycappuccino_storage.ycappuccino_core default need to have a interaction with client

from . import framework


def init(root_path=None, app=None, layers=None, bundle_prefix=None,  port=9000):
    framework.init(root_path, app, layers, bundle_prefix, port)


def start():
    framework.start()
