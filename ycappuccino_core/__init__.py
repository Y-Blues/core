# YCappuccino ycappuccino_storage.ycappuccino_core default need to have a interaction with client

from .framework import Framework

fw: Framework = None
def init(application_yaml):
    global fw
    fw = Framework.get_framework()
    fw.init(application_yaml)

def start():
    global fw

    fw.start()
