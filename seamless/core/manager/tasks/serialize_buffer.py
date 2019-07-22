from . import Task, process_pool

from collections import namedtuple
Serialization = namedtuple("Serialization",["value_id", "celltype"])

from ...protocol import serialize

class SerializeBufferTask(Task):
    _executor = process_pool

    @property
    def refkey(self):
        return Serialization(id(self.value), self.celltype)

    def __init__(self, manager, value, celltype): 
        self.value = value
        self.celltype = celltype
        super().__init__(manager)      

    def _run(self): # not async, since we run in ProcessPoolExecutor
        return serialize(self.value, self.celltype)


