from . import Task, process_pool

from collections import namedtuple
Serialization = namedtuple("Serialization",["value_id", "celltype"])

class SerializeBufferTask(Task):
    _executor = process_pool

    @property
    def refkey(self):
        return Serialization(id(self.value), self.celltype)

    def __init__(self, manager, value, celltype): 
        super.__init__(manager)      
        if self._realtask is not None:
            return
        self.value = value
        self.celltype = celltype

    async def _run(self):
        raise NotImplementedError


