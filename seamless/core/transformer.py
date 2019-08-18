"""
NOTE: in theory, a transformer should have a "copy" attribute,
 indicating if the input arguments will be protected against writing
In practice, the input arguments, even if read from checksum-to-value cache,
 will be in a subprocess. So even if they are modified, there is no
 contamination of cache values.
"""
from collections import OrderedDict
import asyncio

from .worker import Worker, InputPin, OutputPin
from .status import StatusReasonEnum

class Transformer(Worker):
    _checksum = None
    debug = False

    def __init__(self, transformer_params, *,  stream_params=None):
        self.code = InputPin(self, "code", "python", "transformer")
        self._pins = {"code":self.code}
        self._output_name = None
        self._transformer_params = OrderedDict()
        self._stream_params = stream_params # TODO: validate
        forbidden = ("code",)
        for p in sorted(transformer_params.keys()):
            if p in forbidden:
                raise ValueError("Forbidden pin name: %s" % p)
            param = transformer_params[p]
            self._transformer_params[p] = param
            pin = None
            io, celltype, subcelltype = None, None, None
            if isinstance(param, str):
                io = param
            elif isinstance(param, (list, tuple)):
                io = param[0]
                if len(param) > 1:
                    celltype = param[1]
                if len(param) > 2:
                    subcelltype = param[2]
                if len(param) > 3:
                    raise ValueError(param)
            elif isinstance(param, dict):
                io = param["io"]
                celltype = param.get("celltype", celltype)
                subcelltype = param.get("subcelltype", subcelltype)
            else:
                raise ValueError((p, param))
            if io == "input":
                pin = InputPin(self, p, celltype, subcelltype)
            elif io == "output":
                pin = OutputPin(self, p, celltype, subcelltype)
                assert self._output_name is None  # can have only one output
                self._output_name = p
            else:
                raise ValueError(io)
            
            if pin is not None:
                self._pins[p] = pin

        if self._output_name is None:
            raise Exception("Transformer must have an output")
        super().__init__()

    def _set_context(self, ctx, name):
        has_ctx = self._context is not None
        super()._set_context(ctx, name)        
        if not has_ctx:
            self._get_manager().register_transformer(self)

    @property
    def checksum(self):
        checksum = self._checksum
        if checksum is not None:
            checksum = checksum.hex()
        return checksum

    @property
    def void(self):
        return self._void

    def clear_exception(self):
        manager = self._get_manager()
        tcache = manager.cachemanager.transformation_cache
        tcache.clear_exception(self)

    def touch(self):
        """If a transformer was cancelled, relaunch it.
        If running, the transformation job Future is returned"""
        manager = self._get_manager()
        tcache = manager.cachemanager.transformation_cache
        return tcache.touch_transformer(self)

    def shell(self):
        raise NotImplementedError #livegraph branch

    def _get_status(self):
        from .status import status_transformer
        status = status_transformer(self)
        return status

    @property
    def status(self):
        """The computation status of the transformer"""
        from .status import format_worker_status
        status = self._get_status()
        statustxt = format_worker_status(status)
        return "Status: " + statustxt 

    @property
    def exception(self):
        if not self._void:
            return None
        if self._status_reason != StatusReasonEnum.ERROR:
            return None
        manager = self._get_manager()
        transformation_cache = manager.cachemanager.transformation_cache
        transformation = transformation_cache.transformer_to_transformations[self]
        return transformation_cache.transformation_exceptions[transformation]

    @property
    def void(self):
        return self._void

    async def _get_buffer(self):
        from .protocol.get_buffer import get_buffer_async
        if self._checksum is None:
            return None
        buffer_cache = self._get_manager().cachemanager.buffer_cache
        buffer = await get_buffer_async(self._checksum, buffer_cache)
        return buffer

    async def _get_value(self):
        from .protocol.deserialize import deserialize
        manager = self._get_manager()
        livegraph = manager.livegraph
        downstreams = livegraph.transformer_to_downstream[self]
        if not len(downstreams):
            return None
        first_output = downstreams[0].write_accessor.target()
        outputpin = self._pins[self._output_name]
        output_celltype = outputpin.celltype
        if output_celltype is None:
            output_celltype = first_output._celltype
        checksum = self._checksum
        buffer = await self._get_buffer()
        if buffer is None:
            return None
        value = await deserialize(buffer, checksum, output_celltype, True)
        return value

    @property
    def buffer(self):
        task = self._get_buffer()
        loop = asyncio.get_event_loop()
        future = asyncio.ensure_future(task)
        loop.run_until_complete(future)
        return future.result()

    @property
    def value(self):
        task = self._get_value()
        loop = asyncio.get_event_loop()
        future = asyncio.ensure_future(task)
        loop.run_until_complete(future)
        return future.result()

    def destroy(self, *, from_del=False):
        if not from_del:
            self._get_manager()._destroy_transformer(self)
        super().destroy(from_del=from_del)

    def __str__(self):
        ret = "Seamless transformer: " + self._format_path()
        return ret

def transformer(params, *, stream_params=None):
    """TODO: port documentation from 0.1"""
    return Transformer(params, stream_params=stream_params)
