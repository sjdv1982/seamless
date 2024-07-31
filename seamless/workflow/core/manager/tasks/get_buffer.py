from . import BackgroundTask

class GetBufferTask(BackgroundTask):
    @property
    def refkey(self):
        return self.checksum

    def __init__(self,
        manager, checksum
    ):
        self.checksum = checksum
        super().__init__(manager)

    async def _run(self):
        checksum = self.checksum
        if checksum is None:
            return None
        manager = self.manager()
        if manager is None or manager._destroyed:
            return
        cachemanager = manager.cachemanager
        result = await cachemanager.fingertip(checksum)
        assert result is None or isinstance(result, bytes)
        return result