import asyncio

class PollingObserver:
    _active = True
    def __init__(self, ctx, path, callback, polling_interval):
        if not isinstance(ctx, Context):
            raise TypeError(type(ctx))
        self.ctx = ctx
        self.path = path
        self.polling_interval = polling_interval
        self.callback = callback
        self.value = None
        self.loop = asyncio.ensure_future(self._run())
    
    async def _run(self):
        while self._active:
            self._run_once()
            await asyncio.sleep(self.polling_interval)

    def _run_once(self):
        ctx = self.ctx
        value = ctx
        try:
            for p in self.path:
                if isinstance(p, int):                    
                    value = value[p]
                else:
                    value = getattr(value, p)
                if not isinstance(value, (Base, Silk, MixedObject)):
                    if callable(value):
                        value = value()
            if value is None:
                return
            if value == self.value:
                return
            self.value = value
            self.callback(value)
        except Exception:
            pass
    
    def stop(self):
        self._active = False
        ctx = self.ctx
        ctx._observers.pop(self)

from .Context import Context, Base
from ..silk.Silk import Silk
from ..mixed import MixedObject