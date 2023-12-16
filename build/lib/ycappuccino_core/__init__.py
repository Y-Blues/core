# YCappuccino ycappuccino_storage.ycappuccino_core default need to have a interaction with client

from . import framework


def init(root_path=None, app=None, layers=None,  port=9000):
    framework.init(root_path, app, layers, port)


def start():
    framework.start()
