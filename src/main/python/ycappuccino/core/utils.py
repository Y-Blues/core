"""
Registries shared by the framework and the @App / @Layer decorators.

This module has no dependency, so that decorators and models can be imported outside
of the framework (e.g. by the pyscript client).
"""

# attributes set on the classes decorated with @Layer / @App
LAYER_ATTRIBUTE = "__ycappuccino_layer__"
APP_ATTRIBUTE = "__ycappuccino_app__"

# class name -> layer / app name
map_layer_class = {}
map_app_class = {}

# module name -> file path of the modules declaring @Item models
bundle_models_loaded_path_by_name = {}
