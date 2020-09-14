from collections import namedtuple
import asyncio

from . import BackgroundTask
from ...protocol.serialize import serialize

Serialization = namedtuple("Serialization",["value_id", "celltype"])

class SerializeToBufferTask(BackgroundTask):
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
        try:
            result = await serialize(self.value, self.celltype, use_cache=self.use_cache)
        except asyncio.CancelledError as exc:
            raise exc from None
        except Exception as exc:
            raise type(exc)(exc) from None
        return result
