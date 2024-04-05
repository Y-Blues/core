import abc

import inspect
import types
from typing import Optional

from pelix.ipopo.decorators import Instantiate, Requires, Provides, ComponentFactory


class YCappuccinoComponent(abc.ABC):
    pass

class Test2(YCappuccinoComponent):
    name = "toto"

    def __init__(self, toto: str):
        self.toto: str = toto

class Test(YCappuccinoComponent):
    def __init__(self, tata: Optional[Test2], toto:str = "test"):
        self.toto: str = toto
        self.tata: Test2 = tata


sign = inspect.signature(Test.__init__)
print(sign)
for key, item in sign.parameters.items():
    print("key",key)
    print("default", item.default)
    if type(item.annotation).__name__ == '_UnionGenericAlias':
        print(item.annotation.__args__[0].__name__)
    else:
        print("type",item.annotation.__name__)

# @ComponentFactory(Test.__class__.__name__)
# @Provides(Test.__class__.__name__)
# @Requires('_config', Test2.__class__.__name__)
# @Instantiate(Test.__name__)
# class Test_ipopo(Proxy):
#
#     def __int__(self):
#         self.toto = None
#         self.tata = None
#
#
#     def validate(self):
#         self._objname: str = Test.__str__()
#         self._obj: any = Test(self.toto,self.tata)
