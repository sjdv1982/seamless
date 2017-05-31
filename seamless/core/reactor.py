#totally synchronous, for GUI

import os
import traceback
from functools import partial
from collections import OrderedDict

from .macro import macro
from .worker import Worker, InputPin, EditPin, OutputPin
from .cell import Cell, PythonCell
from .pysynckernel import Reactor as KernelReactor
from ..dtypes.objects import PythonBlockObject

from .. import dtypes
from .. import silk
import seamless

#TODO: on_disconnect? don't do anything if self._destroyed

reactor_param_docson = {} #TODO, adapt from transformer and from reactor.silk
currdir = os.path.dirname(__file__)
silk.register(
  open(os.path.join(currdir, "reactor.silk")).read(),
  doc = "Reactor pin parameters",
  docson = reactor_param_docson  #("json", "docson")
)

reactor_params = {
  "*": "silk.ReactorPin",
}
dtypes.register(
  ("json", "seamless", "reactor_params"),
  typeschema = reactor_params, #("json", "typeschema")
  docson = {
    "*": "Reactor pin parameters",
  },
  doc = "Reactor parameters"
)

class Reactor(Worker):
    """
    This is the main-thread part of the worker
    """
    _required_code_type = PythonCell.CodeTypes.ANY

    def __init__(self, reactor_params):
        super().__init__()

        from .macro import get_macro_mode
        self.state = {}
        self.outputs = {}
        self.code_start = InputPin(self, "code_start", ("text", "code", "python"))
        self.code_update = InputPin(self, "code_update", ("text", "code", "python"))
        self.code_stop = InputPin(self, "code_stop", ("text", "code", "python"))
        kernel_inputs = {}
        self._io_attrs = ["code_start", "code_update", "code_stop"]
        self._pins = {
                        "code_start": self.code_start,
                        "code_update": self.code_update,
                        "code_stop": self.code_stop,
                     }
        self._reactor_params = OrderedDict()
        for p in sorted(reactor_params.keys()):
            #TODO: check that they don't overlap with reactor attributes (.path, .name, ...),
            #     ...and with code_start, code_update, code_stop, or is that allowed  (???)
            param = reactor_params[p]
            self._reactor_params[p] = param
            dtype = param.get("dtype", None)
            if isinstance(dtype, list):
                dtype = tuple(dtype)
            if param["pin"] == "input":
                pin = InputPin(self, p, dtype)
                kernel_inputs[p] = dtype, (dtype != "signal")
            elif param["pin"] == "output":
                pin = OutputPin(self, p, dtype)
                self.outputs[p] = dtype
            elif param["pin"] == "edit":
                pin = EditPin(self, p, dtype)
                kernel_inputs[p] = dtype, param.get("must_be_defined", True)
                self.outputs[p] = dtype
            self._io_attrs.append(p)
            self._pins[p] = pin


        self.reactor = KernelReactor(
            self,
            kernel_inputs,
            self.outputs,
        )
        if get_macro_mode():
            for pin in self._pins.values():
                if isinstance(pin, OutputPin):
                    pin.cell() #auto-create a cell

    def _shell(self, toplevel=True):
        p = self._find_successor()
        return p.reactor.namespace, "Reactor %s" % str(self)

    @property
    def reactor_params(self):
        return self._reactor_params

    def output_update(self, name, value):
        self._pins[name].send_update(value)

    def updates_processed(self, updates):
        self._pending_updates -= updates

    def set_context(self, context):
        Worker.set_context(self, context)
        for pin in self._pins.values():
            pin.set_context(context)
        return self

    def receive_update(self, input_pin, value, resource_name):
        self._pending_updates += 1

        if self._pins[input_pin].dtype == "signal":
            self.reactor.process_input(input_pin, value, resource_name)
        else:
            work = partial(self.reactor.process_input, input_pin, value, resource_name)
            seamless.add_work(work)

    def receive_registrar_update(self, registrar_name, key, namespace_name):
        #TODO: this will only work for same-namespace (thread) kernels
        self._pending_updates += 1
        f = self.reactor.process_input
        value = registrar_name, key, namespace_name
        work = partial(f, "@REGISTRAR", value)
        seamless.add_work(work, priority=True)

    def __dir__(self):
        return object.__dir__(self) + list(self._pins.keys())

    def destroy(self):
        if self._destroyed:
            return
        try:
            reactor = self.reactor
        except AttributeError:
            pass
        else:
            reactor.destroy()

        # free all input and output pins
        for attr in self._io_attrs:
            value = getattr(self, attr)
            if value is None:
                continue

            setattr(self, attr, None)
            del value
        super().destroy()

    def __del__(self):
        try:
            self.destroy()

        except Exception as err:
            print(err)
            pass

# @macro takes nothing, a type, or a dict of types
@macro(type=("json", "seamless", "reactor_params"),with_context=False)
def reactor(kwargs):
    from seamless.core.reactor import Reactor #code must be standalone
    #TODO: remapping, e.g. output_finish, destroy, ...
    return Reactor(kwargs)

from .context import Context
