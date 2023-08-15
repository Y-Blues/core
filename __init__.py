# YCappuccino ycappuccino.core default need to have a interaction with client

import framework


def init(root_path=None, app=None, port=9000):
    framework.init(root_path, app, port)


def start():
    framework.start()
