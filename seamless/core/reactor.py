from collections import OrderedDict

from .worker import Worker, InputPin, OutputPin, EditPin
from .status import StatusReasonEnum

class Reactor(Worker):
    _pending = False
    _last_outputs = None

    #can't have with_schema because multiple outputs are possible
    # reactors will have to construct their own Silk objects from schema pins
    def __init__(self, reactor_params, pure):
        self.outputs = {}
        self.inputs = {
            "code_start":("python", "reactor", True),
            "code_stop":("python", "reactor", True),
            "code_update":("python", "reactor", True),
        }
        self.code_start = InputPin(self, "code_start", "python", "reactor")
        self.code_update = InputPin(self, "code_update", "python", "reactor")
        self.code_stop = InputPin(self, "code_stop", "python", "reactor")
        self._pins = {
            "code_start": self.code_start,
            "code_update": self.code_update,
            "code_stop": self.code_stop,
        }
        self._reactor_params = OrderedDict()
        assert pure in (True, False)
        self._pure = pure

        forbidden = list(self.inputs.keys())
        for p in sorted(reactor_params.keys()):
            if p in forbidden:
                raise ValueError("Forbidden pin name: %s" % p)
            param = reactor_params[p]
            self._reactor_params[p] = param
            pin = None
            io, celltype, subcelltype = None, None, None
            must_be_defined = True
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
                must_be_defined = param.get("must_be_defined", must_be_defined)
            else:
                raise ValueError((p, param))
            if not must_be_defined:
                raise NotImplementedError # must_be_defined must be True for now
            if io == "input":
                pin = InputPin(self, p, celltype, subcelltype)
                self.inputs[p] = celltype, subcelltype, must_be_defined
            elif io == "output":
                pin = OutputPin(self, p, celltype, subcelltype)
                self.outputs[p] = celltype, subcelltype
            elif io == "edit":
                pin = EditPin(self, p, celltype, subcelltype)
                self.inputs[p] = celltype, subcelltype, must_be_defined
                self.outputs[p] = celltype, subcelltype
            else:
                raise ValueError(io)

            if pin is not None:
                self._pins[p] = pin
        super().__init__()

    @property
    def pure(self):
        return self._pure

    def _set_context(self, ctx, name):
        has_ctx = self._context is not None
        super()._set_context(ctx, name)        
        if not has_ctx:
            self._get_manager().register_reactor(self)

    def _get_status(self):
        from .status import status_reactor
        status = status_reactor(self)
        return status

    @property
    def status(self):
        """The computation status of the reactor"""
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
        pinname, exc = manager.cachemanager.reactor_exceptions[self]
        return "Pin name: %s\n"  % pinname + exc

    def shell(self):
        raise NotImplementedError #livegraph branch

    def destroy(self, *, from_del):
        if not from_del:
            self._get_manager()._destroy_reactor(self)
        super().destroy(from_del=from_del)

    def __str__(self):
        ret = "Seamless reactor: " + self._format_path()
        return ret


def reactor(params, pure=False):
    """TODO: port documentation from 0.1"""
    return Reactor(params, pure=pure)
