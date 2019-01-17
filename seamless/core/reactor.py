from collections import OrderedDict

from .worker import Worker, InputPin, OutputPin
from .protocol import content_types

class Reactor(Worker):
    #can't have with_schema because multiple outputs are possible
    # reactors will have construct their own Silk objects from schema pins
    def __init__(self, reactor_params):
        self.outputs = {}
        self.inputs = {
            "code_start":("ref", "pythoncode", "reactor", True),
            "code_stop":("ref", "pythoncode", "reactor", True),
            "code_update":("ref", "pythoncode", "reactor", True),
        }
        self.code_start = InputPin(self, "code_start", "ref", "pythoncode", "python")
        self.code_update = InputPin(self, "code_update", "ref", "pythoncode", "python")
        self.code_stop = InputPin(self, "code_stop", "ref", "pythoncode", "python")
        self._pins = {
                        "code_start": self.code_start,
                        "code_update": self.code_update,
                        "code_stop": self.code_stop,
                     }
        self._reactor_params = OrderedDict()

        forbidden = list(self.inputs.keys())
        for p in sorted(reactor_params.keys()):
            if p in forbidden:
                raise ValueError("Forbidden pin name: %s" % p)
            param = reactor_params[p]
            self._reactor_params[p] = param
            pin = None
            io, transfer_mode, access_mode, content_type = None, "copy", None, None
            must_be_defined = True
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
                must_be_defined = param.get("must_be_defined", must_be_defined)
            else:
                raise ValueError((p, param))
            if content_type is None and access_mode in content_types:
                content_type = access_mode
            if io == "input":
                pin = InputPin(self, p, transfer_mode, access_mode, content_type)
                self.inputs[p] = transfer_mode, access_mode, content_type, must_be_defined
            elif io == "output":
                pin = OutputPin(self, p, transfer_mode, access_mode, content_type)
                self.outputs[p] = transfer_mode, access_mode, content_type
            elif io == "edit":
                pin = EditPin(self, p, transfer_mode, access_mode, content_type)
                self.inputs[p] = transfer_mode, access_mode, content_type, must_be_defined
                self.outputs[p] = transfer_mode, access_mode, content_type
            else:
                raise ValueError(io)

            if pin is not None:
                self._pins[p] = pin
        super().__init__()

    def __str__(self):
        ret = "Seamless reactor: " + self._format_path()
        return ret


def reactor(params):
    """TODO: port documentation from 0.1"""
    return Reactor(params)

