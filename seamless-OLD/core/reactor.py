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

from . import IpyString
from .. import dtypes
from .. import silk
import seamless

#TODO: on_disconnect? don't do anything if self._destroyed

reactor_param_docson = {} #TODO, adapt from transformer
currdir = os.path.dirname(__file__)
"""
silk.register(
  open(os.path.join(currdir, "reactor.silk")).read(),
  doc = "Reactor pin parameters",
  docson = reactor_param_docson  #("json", "docson")
)
"""
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
    _shell_rae = None

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

            if p == "@shell":
                rae = reactor_params[p]
                rae = rae.strip(".").split(".")
                self._shell_rae = rae
                continue

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

    def __str__(self):
        ret = "Seamless reactor: " + self.format_path()
        return ret

    def _shell(self, toplevel=True):
        p = self._find_successor()
        namespace = p.reactor.namespace
        if self._shell_rae is not None:
            for attr in self._shell_rae:
                namespace = namespace[attr]
        return namespace, str(self)

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
        work = partial(f, "@REGISTRAR", value, None)
        seamless.add_work(work, priority=True)

    def __dir__(self):
        return object.__dir__(self) + list(self._pins.keys())

    @property
    def error(self):
        """Returns a text representation of any exception (with traceback)
        that occurred during reactor execution"""
        import traceback
        if self.reactor.exception is None:
            return None
        else:
            exc, tb = self.reactor.exception
            tbstr = "".join(traceback.format_exception(type(exc), exc, tb))
            return IpyString(tbstr)

    def status(self):
        """The computation status of the reactor
        Returns a dictionary containing the status of all pins that are not OK.
        If all pins are OK, returns the status of the reactor itself: OK or pending
        """
        result = {}
        for pinname, pin in self._pins.items():
            s = pin.status()
            if s != self.StatusFlags.OK.name:
                result[pinname] = s
        rc = self.reactor
        for pinname in rc._pending_inputs:
            if pinname not in result:
                result[pinname] = self.StatusFlags.PENDING.name
        if len(result):
            return result
        if rc._pending_updates:
            return self.StatusFlags.PENDING.name
        if self.error is not None:
            return self.StatusFlags.ERROR.name            
        return self.StatusFlags.OK.name

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
def reactor(params):
    """Defines a reactor worker.

Reactors react upon changes in their input cells.
Reactors are connected to their input cells via inputpins. In addition, reactors
may manipulate output cells via outputpins. Finally, a cell may be both an
input and an output of the reactor, by connecting it via an editpin.
The pins are declared in the `params` parameter (see below).

In addition, all reactors have three implicit inputpins named `code_start`,
`code_update` and `code_stop`. Each pin must be connected to a Python cell
( `dtype=("text", "code", "python")` ), containing a code block.

The reactor will start as soon as all input cells (including the three code cells)
have been defined. The startup of the reactor will trigger the execution of the
code in the `code_start` cell.

Any change in the inputpins (including at startup)
will trigger the execution of the `code_update` cell. The `code_stop` cell is
invoked when the reactor is destroyed.

As of seamless 0.1, macro re-evaluation destroys and re-creates all reactors
created by the macro, unless the macro has caching enabled.

All three code cells are executed in the same namespace. The namespace contains
an object called `PINS`. This object can be queried for pin objects: a pin
called `spam` is accessible as pin object ``PINS.spam``. The namespace also
contains IDENTIFIER, which is guaranteed to be unique for each reactor
instance.

Every inputpin and editpin object contains a ``get()`` method that
returns the value.
As of seamless 0.1, the `value` property is identical to ``pin.get()``.

Every inputpin and editpin object has a property `updated`, which is True if
the pin has been updated since the last time `code_update` was executed.

Every outputpin and editpin has a ``set(value)`` method.
In case of a signal outputpin, ``set()`` is to be invoked without argument.
Invoking ``set()`` on a signal outputpin will propagate the signal as fast as possible:
    - If set from the main thread: immediately. Downstream workers are
      notified and activated (if synchronous) before set() returns
    - If set from another thread: as soon as ``seamless.run_work`` is called.
      Then, downstream workers are notified and activated before any other
      non-signal notification.

As of seamless 0.1, all reactors are synchronous (blocking): their code is
executed in the main thread. Therefore, seamless and IPython are non-responsive
while reactor code is executing, and reactor code should return as soon as
possible. Therefore, if they perform long computations, reactors should spawn
their own threads or processes from within their code.

Invoke ``reactor.status()`` to get the current status of the reactor

Invoke ``shell(reactor)`` to create an IPython shell of the reactor namespace

``pin.connect(cell)`` connects an outputpin to a cell

``cell.connect(pin)`` connects a cell to an inputpin

``pin.cell()`` returns or creates a cell that is connected to that pin

Parameters
----------

    params: dict
        A dictionary containing the reactor parameters.
        As of seamless 0.1, each (name,value) item represents a reactor pin:

        -  name: string
            name of the pin

        -  value: dict
            with the following items:

            - pin: string
                must be "input", "output" or "edit"
            - dtype: string or tuple of strings
                Describes the dtype of the cell(s) connected to the pin.
                As of seamless 0.1, the following data types are understood:

                -   "int", "float", "bool", "str", "json", "cson", "array", "signal"
                -   "text", ("text", "code", "python"), ("text", "code", "ipython")
                -   ("text", "code", "silk"), ("text", "code", "slash-0")
                -   ("text", "code", "vertexshader"), ("text", "code", "fragmentshader"),
                -   ("text", "html"),
                -   ("json", "seamless", "transformer_params"),
                    ("cson", "seamless", "transformer_params"),
                -   ("json", "seamless", "reactor_params"),
                    ("cson", "seamless", "reactor_params")

            - must_be_defined: bool
               default = True

               In case of edit pins, if `must_be_defined` is False, the reactor
               will start up  even if the connected cell does not yet have a
               defined value.

        Since "reactor" is a macro, the dictionary can also be provided
        in the form of a cell of dtype ("json", "seamless", "reactor_params")
"""
    from seamless.core.reactor import Reactor #code must be standalone
    return Reactor(params)

from .context import Context
