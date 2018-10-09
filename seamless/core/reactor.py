import os
import traceback
from functools import partial
from collections import OrderedDict
import threading

from .worker import Worker, InputPin, EditPin, OutputPin
from .cell import Cell, PythonCell
from .pysynckernel import Reactor as KernelReactor

from . import IpyString

from . import get_macro_mode, macro_register
from .protocol import content_types

class Reactor(Worker):
    """
    This is the main-thread part of the reactor
    """

    active = False
    _destroyed = False
    _queue = []

    #can't have with_schema because multiple outputs are possible
    # reactors will have construct their own Silk objects from schema pins
    def __init__(self, reactor_params):
        self._immediate_id = 0
        self.state = {}
        self.outputs = {}
        self.inputs = {
            "code_start":("ref", "pythoncode", "reactor", True),
            "code_stop":("ref", "pythoncode", "reactor", True),
            "code_update":("ref", "pythoncode", "reactor", True),
        }
        self.code_start = InputPin(self, "code_start", "ref", "pythoncode", "python")
        self.code_update = InputPin(self, "code_update", "ref", "pythoncode", "python")
        self.code_stop = InputPin(self, "code_stop", "ref", "pythoncode", "python")
        self._io_attrs = ["code_start", "code_update", "code_stop"]
        self._pins = {
                        "code_start": self.code_start,
                        "code_update": self.code_update,
                        "code_stop": self.code_stop,
                     }
        self._reactor_params = OrderedDict()
        self._delay_update = 0

        forbidden = list(self.inputs.keys())
        for p in sorted(reactor_params.keys()):
            if p in forbidden:
                raise ValueError("Forbidden pin name: %s" % p)
            param = reactor_params[p]
            self._reactor_params[p] = param
            pin = None
            io, transfer_mode, access_mode, content_type = None, "ref", None, None
            must_be_defined = True
            #TODO: change "ref" to "copy" once transport protocol works
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
                self._io_attrs.append(p)
                self._pins[p] = pin
        super().__init__()

    def _update_immediate_id(self):
        self._immediate_id += 1

    def activate(self, only_macros):
        if self.active:
            return
        self.reactor = KernelReactor(
            self,
            self.inputs,
            self.outputs,
        )
        self.reactor.activate()
        self.active = True
        self._queue = []
        super().activate(only_macros)

    def __str__(self):
        ret = "Seamless reactor: " + self._format_path()
        return ret

    def _shell(self, access_mode):
        assert access_mode is None
        return self.reactor.namespace, self.code_update, str(self)

    def output_update(self, name, value, preliminary, priority, spontaneous):
        # This will be called by embedded reactors
        # If these reactors launch their own threads, it will be from a different thread
        #TODO: adapt for if the embedded reactor is in a different process
        if (priority or preliminary or spontaneous) and \
          threading.current_thread() is threading.main_thread():
            self._pins[name].send_update(value, preliminary=preliminary)
        else:
            #print("output_update", (name, value, preliminary))
            self._queue.append((name, value, preliminary))

    def flush(self):
        #TODO: adapt for if the embedded reactor is in a different process
        queue, self._queue = self._queue, [] #queue = self._queue and self._queue = []
        for item in queue:
            name, value, preliminary = item
            self._pins[name].send_update(value, preliminary=preliminary)

    def updates_processed(self, updates):
        self._pending_updates -= updates
        self.flush()

    def process_input(self, id, input_pin, value):
        immediate = (id == self._immediate_id)
        self.reactor.process_input(input_pin, value, immediate)

    def receive_update(self, input_pin, value, checksum, access_mode, content_type):
        #print("receive_update", input_pin, value, self.active)
        if self._destroyed:
            return
        if not self.active:
            self._delay_update += 1
            if self._delay_update == 100:
                raise Exception #reactor doesn't get activated, for some reason
            work = partial(self.receive_update, input_pin, value, checksum, access_mode, content_type)
            self._get_manager().workqueue.append(work)
            return
        self._delay_update = 0
        if checksum is None and value is not None:
            checksum = str(value) #KLUDGE; as long as structured_cell doesn't compute checksums...
        if not self._receive_update_checksum(input_pin, checksum):
            return
        self._pending_updates += 1

        if self.inputs[input_pin][0] == "signal":
            self.reactor.process_input(input_pin, value, True)
        else:
            self._update_immediate_id()
            work = partial(self.process_input, self._immediate_id, input_pin, value)
            self._get_manager().workqueue.append(work)

    def __dir__(self):
        return object.__dir__(self) + list(self._pins.keys())

    '''
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
    '''

    def status(self):
        """The computation status of the reactor
        Returns a dictionary containing the status of all pins that are not OK.
        If all pins are OK, returns the status of the reactor itself: OK or pending
        """
        result = {}
        for pinname, pin in self._pins.items():
            s = pin.status()
            if s != self.StatusFlags.OK.name:
                if s == "UNDEFINED":
                    if pinname in self.inputs and not self.inputs[pinname][3]:
                        continue
                result[pinname] = s
        rc = self.reactor
        for pinname in rc._pending_inputs:
            if pinname not in result:
                result[pinname] = self.StatusFlags.PENDING.name
        if len(result):
            return result
        if rc._pending_updates:
            return self.StatusFlags.PENDING.name
        if self.reactor.exception is not None:
            return self.StatusFlags.ERROR.name
        return self.StatusFlags.OK.name

    def destroy(self, from_del=False):
        if from_del:
            return
        if not self.active:
            return
        if self._destroyed:
            return
        reactor = self.reactor
        reactor.destroy()
        super().destroy()

    def full_destroy(self,from_del=False):
        self.self.destroy(from_del=from_del)

def reactor(params):
    """Defines a reactor worker.

Reactors react upon changes in their input cells.
Reactors are connected to their input cells via inputpins. In addition, reactors
may manipulate output cells via outputpins. Finally, a cell may be both an
input and an output of the reactor, by connecting it via an editpin.
The pins are declared in the `params` parameter (see below).

In addition, all reactors have three implicit inputpins named `code_start`,
`code_update` and `code_stop`. Each pin must be connected to a Python cell
containing a code block.

The reactor will start as soon as all input cells (including the three code cells)
have been defined. The startup of the reactor will trigger the execution of the
code in the `code_start` cell.

Any change in the inputpins (including at startup)
will trigger the execution of the `code_update` cell. The `code_stop` cell is
invoked when the reactor is destroyed.

All three code cells are executed in the same namespace. The namespace contains
an object called `PINS`. This object can be queried for pin objects: a pin
called `spam` is accessible as pin object ``PINS.spam``. The namespace also
contains IDENTIFIER, which is guaranteed to be unique for each reactor
instance.

Every inputpin and editpin object contains a ``get()`` method that
returns the value.
As of seamless 0.2, the `value` property is identical to ``pin.get()``.

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

As of seamless 0.2, all reactors are synchronous (blocking): their code is
executed in the main thread. Therefore, seamless and IPython are non-responsive
while reactor code is executing, and reactor code should return as soon as
possible. Therefore, if they perform long computations, reactors should spawn
their own threads or processes from within their code.

Invoke ``reactor.status()`` to get the current status of the reactor

Invoke ``shell(reactor)`` to create an IPython shell of the reactor namespace

Reactors can be created or connected only in macro mode

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
            TODO: document
            - must_be_defined: bool
               default = True

               In case of edit pins, if `must_be_defined` is False, the reactor
               will start up  even if the connected cell does not yet have a
               defined value.

"""
    return Reactor(params)

from .context import Context
