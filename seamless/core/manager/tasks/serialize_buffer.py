from collections import namedtuple

from . import Task
from ...protocol import serialize

Serialization = namedtuple("Serialization",["value_id", "celltype"])

class SerializeToBufferTask(Task):
    @property
    def refkey(self):
        return Serialization(id(self.value), self.celltype)

    def __init__(self, manager, value, celltype): 
        self.value = value
        self.celltype = celltype
        super().__init__(manager)      

    async def _run(self): 
        taskmanager = self.manager().taskmanager
        loop = taskmanager.loop
        result = await serialize(self.value, self.celltype)
        return result 


