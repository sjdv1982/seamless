import numpy as np
from collections import namedtuple

from . import BackgroundTask
from ...protocol.deserialize import deserialize

Deserialization = namedtuple("Deserialization",["checksum", "celltype", "copy"])

class DeserializeBufferTask(BackgroundTask):
    @property
    def refkey(self):
        ### return Deserialization(self.checksum, self.celltype, self.copy)
        return None ###
                    # TODO: if the caller of this task modifies the return value,
                    #   that will modify the return value of the reftask as well! (and vice versa)
                    # Spooky effects at a distance!
                    # This causes the highlevel/context2.py test to fail, for example


    def __init__(self, manager, buffer, checksum, celltype, copy):
        assert buffer is None or isinstance(buffer, bytes)
        self.buffer = buffer
        self.checksum = checksum
        assert checksum.hex().isalnum() and len(checksum) == 32, checksum
        self.celltype = celltype
        self.copy = copy
        super().__init__(manager)

    async def _run(self):
        result = await deserialize(self.buffer, self.checksum, self.celltype, self.copy)        
        if isinstance(result, np.ndarray):
            buffer_cache.update_buffer_info(self.checksum, "shape", result.shape, update_remote=False)
            buffer_cache.update_buffer_info(self.checksum, "dtype", str(result.dtype))
        buffer_cache.guarantee_buffer_info(self.checksum, self.celltype)
        return result

from ...cache.buffer_cache import buffer_cache