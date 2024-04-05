
"""
decorator for app and layer that is use on component. this allow to know regarding a config what app and layer to user
"""
from .framework import Framework
class App(object):
    # Make copy of original __init__, so we can call it without recursion
    def __init__(self, name:str):

        self.name = name

    def __call__(self, obj):
        Framework.get_framework().add_app(obj.__name__,self.name)
        return obj



class Layer(object):
    # Make copy of original __init__, so we can call it without recursion
    def __init__(self, name):
        self.name = name


    def __call__(self, obj):
        Framework.get_framework().add_layer(obj.__name__,self.name)
        return obj


