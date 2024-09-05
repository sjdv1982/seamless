from seamless import Checksum, Buffer
from . import BackgroundTask
from seamless.checksum.cached_calculate_checksum import cached_calculate_checksum


class CalculateChecksumTask(BackgroundTask):
    @property
    def refkey(self):
        return id(self.buffer)

    def __init__(self, manager, buffer):
        self.buffer = Buffer(buffer).value
        super().__init__(manager)

    async def _run(self) -> Checksum:
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        result = await cached_calculate_checksum(self.buffer)
        result = Checksum(result)
        if self.buffer:
            assert result
        return result
