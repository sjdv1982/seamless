import numpy as np
from collections import namedtuple

from . import BackgroundTask
from seamless.checksum.deserialize import deserialize
from seamless import Checksum

Deserialization = namedtuple("Deserialization", ["checksum", "celltype", "copy"])


class DeserializeBufferTask(BackgroundTask):
    @property
    def refkey(self):
        ### return Deserialization(self.checksum, self.celltype, self.copy)
        return None  ###
        # TODO: if the caller of this task modifies the return value,
        #   that will modify the return value of the reftask as well! (and vice versa)
        # Spooky effects at a distance!
        # This causes the highlevel/context2.py test to fail, for example

    def __init__(self, manager, buffer, checksum: Checksum, celltype, copy):
        assert buffer is None or isinstance(buffer, bytes)
        checksum = Checksum(checksum)
        self.buffer = buffer
        self.checksum = checksum
        self.celltype = celltype
        self.copy = copy
        super().__init__(manager)

    async def _run(self):
        result = await deserialize(self.buffer, self.checksum, self.celltype, self.copy)
        if isinstance(result, np.ndarray):
            buffer_cache.update_buffer_info(
                self.checksum, "shape", result.shape, sync_remote=False
            )
            buffer_cache.update_buffer_info(
                self.checksum, "dtype", str(result.dtype), sync_remote=False
            )
        buffer_cache.guarantee_buffer_info(
            self.checksum, self.celltype, sync_to_remote=True
        )
        return result


from seamless.checksum.buffer_cache import buffer_cache
