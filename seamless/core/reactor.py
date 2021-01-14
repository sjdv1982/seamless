from collections import OrderedDict

from .worker import Worker, InputPin, OutputPin, EditPin
from .status import StatusReasonEnum

class Reactor(Worker):
    _pending = False
    _last_outputs = None

    #can't have with_schema because multiple outputs are possible
    # reactors will have to construct their own Silk objects from schema pins
    def __init__(self, reactor_params):
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
        raise NotImplementedError

    def destroy(self, *, from_del):
        self._get_manager()._destroy_reactor(self)
        super().destroy(from_del=from_del)

    def __str__(self):
        ret = "Seamless reactor: " + self._format_path()
        return ret


def reactor(params):
    """Defines a reactor.

Reactors react upon changes in their input cells.
Reactors are connected to their input cells via inputpins.
In addition, a cell may be both an input and an output of the reactor,
by connecting it via an editpin.
The pins are declared in the `params` parameter (see below).

Finaly, all reactors have three implicit inputpins named `code_start`,
`code_update` and `code_stop`. Each pin must be connected to a Python cell
containing a code block.

The reactor will start as soon as all input cells (including the three code cells)
have been defined. The startup of the reactor will trigger the execution of the
code in the `code_start` cell.

Any change in the inputpins (including at startup)
will trigger the execution of the `code_update` cell. The `code_stop` cell is
invoked when the reactor is destroyed.

Unlike transformer, reactors are not cached. Re-evaluation of reactors in a macro
destroys and re-creates all reactors created by the macro.

All three code cells are executed in the same namespace. The namespace contains
an object called `PINS`. This object can be queried for pin objects: a pin
called `spam` is accessible as pin object ``PINS.spam``.

Every pin object contains a ``get()`` method that
returns the value. The `value` property is identical to ``pin.get()``.

Every pin object has a property `updated`, which is True if
the pin has been updated since the last time `code_update` was executed.

Every outputpin and editpin has a ``set(value)`` method.

All reactors are synchronous (blocking): their code is
executed in the main thread of the main process.
Therefore, Seamless and IPython are non-responsive
while reactor code is executing, and reactor code should return as soon as
possible. Therefore, if they perform long computations, reactors should spawn
their own threads or processes from within their code.

Invoke ``reactor.status()`` to get the current status of the reactor

``pin.connect(cell)`` connects an outputpin to a cell

``cell.connect(pin)`` connects a cell to an inputpin

``pin.cell()`` returns or creates a cell that is connected to that pin

Parameters
----------

    params: dict
        A dictionary containing the reactor parameters.
        Each (name,value) item represents a reactor pin:

        -  name: string
            name of the pin

        -  value: dict
            with the following items:

            - pin: string
                must be "input", "output" or "edit"
            - dtype: string or tuple of strings
                Describes the data type of the cell(s) connected to the pin.
            - must_be_defined: bool
               default = True

               In case of edit pins, if `must_be_defined` is False, the reactor
               will start up  even if the connected cell does not yet have a
               defined value.
    """
    return Reactor(params)
