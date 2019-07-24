from collections import namedtuple

from . import Task
from ...protocol import deserialize

Deserialization = namedtuple("Deserialization",["checksum", "celltype", "copy"])

class DeserializeBufferTask(Task):
    @property
    def refkey(self):
        return Deserialization(self.checksum, self.celltype, self.copy)

    def __init__(self, manager, buffer, checksum, celltype, copy): 
        self.buffer = buffer
        self.checksum = checksum
        self.celltype = celltype
        self.copy = copy
        super().__init__(manager)      

    async def _run(self): 
        result = await deserialize(self.buffer, self.checksum, self.celltype, self.copy)
        return result 


