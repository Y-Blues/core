

map_layer_class = {}
class App(object):
    # Make copy of original __init__, so we can call it without recursion
    def __init__(self, name):
        self.name = name

    def __call__(self, obj):
        map_layer_class[obj.__name__] = self.name
        return obj



map_app_class = {}
class Layer(object):
    # Make copy of original __init__, so we can call it without recursion
    def __init__(self, name, layers):
        self.name = name
        self.layers = layers


    def __call__(self, obj):
        map_app_class[obj.__name__] = self.name
        return obj


