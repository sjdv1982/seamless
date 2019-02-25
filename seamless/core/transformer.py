from collections import OrderedDict

from .worker import Worker, InputPin, OutputPin
from .protocol import content_types

class Transformer(Worker):

    def __init__(self, transformer_params, stream_params = None):
        self.code = InputPin(self, "code", "ref", "pythoncode", "transformer")
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
            io, transfer_mode, access_mode, content_type = None, "copy", None, None
            if isinstance(param, str):
                io = param
            elif isinstance(param, (list, tuple)):
                io = param[0]
                if len(param) > 1:
                    transfer_mode = param[1]
                if len(param) > 2:
                    access_mode = param[2]
                if len(param) > 3:
                    content_type = param[3]
            elif isinstance(param, dict):
                io = param["io"]
                transfer_mode = param.get("transfer_mode", transfer_mode)
                access_mode = param.get("access_mode", access_mode)
                content_type = param.get("content_type", content_type)
            else:
                raise ValueError((p, param))
            if content_type is None and access_mode in content_types:
                content_type = access_mode
            if io == "input":
                pin = InputPin(self, p, transfer_mode, access_mode)
            elif io == "output":
                pin = OutputPin(self, p, transfer_mode, access_mode)
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
        manager = self._get_manager()
        result = manager.transform_cache.transformer_to_level1.get(self)
        if result is not None:
            result = result.get_hash()
        return result

    def destroy(self, *, from_del=False):
        if not from_del:
            self._get_manager()._destroy_transformer(self)
        super().destroy(from_del=from_del)

    def __str__(self):
        ret = "Seamless transformer: " + self._format_path()
        return ret

def transformer(params, stream_params = None):
    """TODO: port documentation from 0.1"""
    return Transformer(params, stream_params)
