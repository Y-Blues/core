#app="all"

"""
Utilities to discover bundle and models to load regarding the configuration and app and layer decorator
"""


from importlib.abc import Loader
import logging

_logger = logging.getLogger(__name__)

bundle_loaded = []

bundle_models_loaded_path_by_name = {}

map_app_layer = {}



class MyLoader(Loader):
    def __init__(self, filename):
        self.filename = filename

    def create_module(self, spec):
        return None  # use default module creation semantics

    def exec_module(self, module):
        with open(self.filename) as f:
            data = f.read()

        # manipulate data some way...

        exec(data, vars(module))