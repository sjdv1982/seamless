import asyncio
import traceback
from copy import deepcopy

class PollingObserver:
    _active = True
    def __init__(self, ctx, path, callback, polling_interval, observe_none=False, params=None):
        if not isinstance(ctx, Context):
            raise TypeError(type(ctx))
        self.ctx = ctx
        self.path = path
        self.polling_interval = polling_interval
        self.callback = callback
        self.observe_none = observe_none
        self.params = params
        self.value = None
        self.loop = asyncio.ensure_future(self._run())
    
    async def _run(self):
        while self._active:
            self._run_once()
            await asyncio.sleep(self.polling_interval)

    def _run_once(self):
        ctx = self.ctx
        if ctx._translating:
            return
        value = ctx
        try:
            for p in self.path:
                if isinstance(p, int):                    
                    value = value[p]
                else:
                    value = getattr(value, p)
                if not isinstance(value, (Base, Silk, MixedObject)):
                    if callable(value):
                        params = self.params
                        if params is None:
                            value = value()
                        else:
                            value = value(**params)
        except Exception:
            return

        if value is None and not self.observe_none:
            return
        if value == self.value:
            return
        self.value = deepcopy(value)
        
        try:
            self.callback(value)
        except Exception:
            print("PollingObserver error:")
            traceback.print_exc()
    
    def destroy(self):
        self._active = False
        ctx = self.ctx
        ctx._observers.remove(self)

from .Context import Context, Base
from ..silk.Silk import Silk
from ..mixed import MixedObject