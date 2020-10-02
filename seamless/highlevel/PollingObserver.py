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
        self.errors = 0

    async def _run(self):
        while 1:
            await asyncio.sleep(self.polling_interval)
            if not self._active:
                break
            self._run_once()

    def _run_once(self):
        class PathException(Exception):
            pass
        ctx = self.ctx
        if ctx._translating:
            return
        value = ctx
        try:
            for pnr, p in enumerate(self.path):
                try:
                    if isinstance(p, int):
                        value = value[p]
                    else:
                        value = getattr(value, p)
                except:
                    raise PathException(self.path[:pnr+1]) from None
                if not isinstance(value, (Base, Silk, MixedObject)):
                    if callable(value):
                        params = self.params
                        if params is None:
                            value = value()
                        else:
                            value = value(**params)
            ok = True
        except PathException as exc:
            path = exc.args[0]
            path = ".".join(path)
            path2 = ".".join(self.path)
            print("PollingObserver error: %s (%s)" % (path, path2))
            ok = False
        except Exception:
            ok = False
            print("PollingObserver error:")
            traceback.print_exc()
        if not ok:
            self.errors += 1
            if self.errors == 3:
                self.destroy()
            return
        else:
            self.errors = 0

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
        try:
            ctx._observers.remove(self)
        except KeyError:
            pass

from .Context import Context, Base
from ..silk.Silk import Silk
from ..mixed import MixedObject