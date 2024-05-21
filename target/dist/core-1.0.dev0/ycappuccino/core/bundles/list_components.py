from ycappuccino.api.core import IListComponent, IActivityLogger
from ycappuccino.api.core_base import YCappuccinoType
from ycappuccino.api.proxy import YCappuccinoRemote

list_component = None

"""

component that aggregate all YCappuccino component 

@author: apisu
"""


class ListComponent(IListComponent):

    def __init__(
        self,
        logger: YCappuccinoType(IActivityLogger, "(name=main)"),
    ) -> None:
        """
        Constructor
        """
        super(ListComponent, self).__init__()
        global list_component
        list_component = self
        self._map_component = {}
        self._logger = logger

    async def bind(self, a_service: YCappuccinoRemote):
        """bind statement for this component"""
        self._map_component[a_service.id()] = a_service

    async def un_bind(self, a_service: YCappuccinoRemote):
        """unbind statement for this component"""
        del self._map_component[a_service.id()]

    def call(self, a_comp_name, a_method):
        if a_comp_name in self._map_component.keys():
            getattr(self._map_component[a_comp_name], a_method)()

    async def start(self):
        self._logger.info("start list component")

    async def stop(self):
        self._logger.info("stop list component")
