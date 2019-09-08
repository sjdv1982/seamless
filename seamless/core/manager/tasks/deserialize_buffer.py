from collections import namedtuple

from . import Task
from ...protocol.deserialize import deserialize

Deserialization = namedtuple("Deserialization",["checksum", "celltype", "copy"])

class DeserializeBufferTask(Task):
    @property
    def refkey(self):
        return Deserialization(self.checksum, self.celltype, self.copy)

    def __init__(self, manager, buffer, checksum, celltype, copy, *, hash_pattern):
        assert buffer is None or isinstance(buffer, bytes)
        self.buffer = buffer
        self.checksum = checksum
        self.celltype = celltype
        self.copy = copy
        self.hash_pattern = hash_pattern
        super().__init__(manager)      

    async def _run(self): 
        if self.hash_pattern is not None:
            raise NotImplementedError  # livegraph branch
        result = await deserialize(self.buffer, self.checksum, self.celltype, self.copy)
        return result 


