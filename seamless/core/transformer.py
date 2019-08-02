"""
NOTE: in theory, a transformer should have a "copy" attribute,
 indicating if the input arguments will be protected against writing
In practice, the input arguments, even if read from checksum-to-value cache,
 will be in a subprocess. So even if they are modified, there is no
 contamination of cache values.
"""
from collections import OrderedDict

from .worker import Worker, InputPin, OutputPin

class Transformer(Worker):
    _checksum = None
    _void = True
    _status_reason = None
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
        
        super().__init__()

    def _set_context(self, ctx, name):
        super()._set_context(ctx, name)
        self._get_manager().register_transformer(self)

    @property
    def checksum(self):
        return self._checksum

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

    #@property
    def status(self):
        """The computation status of the transformer"""
        from .status import status_transformer
        status, reason, pins = status_transformer(self)
        print(status, reason, pins)
        

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
