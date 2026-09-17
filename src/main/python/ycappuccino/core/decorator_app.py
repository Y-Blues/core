"""
decorator for app and layer that is use on component. the framework only loads a class of a layer
when this layer is active regarding application.yml
"""

from ycappuccino.core import utils


class App(object):

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, obj: type) -> type:
        setattr(obj, utils.APP_ATTRIBUTE, self.name)
        utils.map_app_class[obj.__name__] = self.name
        return obj


class Layer(object):

    def __init__(self, name: str) -> None:
        self.name = name

    def __call__(self, obj: type) -> type:
        setattr(obj, utils.LAYER_ATTRIBUTE, self.name)
        utils.map_layer_class[obj.__name__] = self.name
        return obj
