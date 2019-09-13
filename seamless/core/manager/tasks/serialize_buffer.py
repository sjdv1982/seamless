from collections import namedtuple

from . import Task
from ...protocol.serialize import serialize

Serialization = namedtuple("Serialization",["value_id", "celltype"])

class SerializeToBufferTask(Task):
    @property
    def refkey(self):
        if not self.use_cache:
            return None
        return Serialization(id(self.value), self.celltype)

    def __init__(self, manager, value, celltype, use_cache):        
        self.value = value
        self.celltype = celltype
        self.use_cache = use_cache
        super().__init__(manager)      

    async def _run(self): 
        taskmanager = self.manager().taskmanager
        loop = taskmanager.loop
        result = await serialize(self.value, self.celltype, use_cache=self.use_cache)
        return result 


