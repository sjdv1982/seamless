from collections import deque, OrderedDict
import threading
import traceback
import os
import time

from .macro import macro
from .worker import Worker, InputPin, OutputPin
from .cell import Cell, PythonCell
from .pythreadkernel import Transformer as KernelTransformer

from .. import dtypes
from .. import silk

transformer_param_docson = {
  "pin": "Required. Can be \"inputpin\", \"outputpin\", \"bufferpin\"",
  "pinclass": """Optional for inputpin, used to indicate a code inputpin
   or a volatile inputpin.
Required for bufferpin, used to indicate the kind of bufferpin
For inputpin:
  if defined, can be "codefunction", "codeblock"  or "volatile" (other)
  "codefunction" : the code must return a value (contain a return statement)
  "codeblock" : the code is just executed
For inputpin or outputpin:
  "volatile": the cell may change during the transform. Transform code may
   request the volatile value using ()
For bufferpin:
  can be "read", "write" or "modify" """,
  "order": """Optional, only for codeblock inputpins.
Indicates the order of codeblock evaluations (codeblocks with a lower order
get executed first; order must be a positive integer)
Necessary if there are multiple codeblock inputpins.
Changing a codeblock re-executes the codeblock and all codeblocks with a higher
order (unless checkpoint dependencies are defined)""",
  "dtype": "Optional, must be registered with types if defined"
}
currdir = os.path.dirname(__file__)
silk.register(
  open(os.path.join(currdir, "transformer.silk")).read(),
  doc = "Transformer pin parameters",
  docson = transformer_param_docson  #("json", "docson")
)

transformer_params = {
  "*": "silk.SeamlessTransformerPin",
  "_use_codeblock_checkpoints": {
    "dtype": bool,
    "default": False,
  },
  "_codeblock_deps": {
    "dtype": dict,
    "default": {},
  }
}
dtypes.register(
  ("json", "seamless", "transformer_params"),
  typeschema = transformer_params, #("json", "typeschema")
  docson = {
    "*": "Transformer pin parameters",
    "_use_codeblock_checkpoints": """Optional. If defined, indicates
that the code kernel global namespace is saved before each codeblock
evaluation. When there are codeblocks that have changed, the checkpoint
of the lowest-order changed codeblock is restored before all subsequent
codeblocks are evaluated""",
    "_codeblock_deps": """Optional. If defined, must be a dict of lists
indicating the dependencies between codeblocks. The keys of the dict are
codeblock inputpin names, and so are the items in the lists. For each codeblock,
the dependency list must be a subset of all codeblocks with a lower "order"
value (by default, the dependency list consists of all of those codeblocks)
Defining _codeblock_deps also changes the codeblock checkpoints from a
linear stack to a dependency tree of sub-checkpoints that are merged.
"""
  },
  doc = "Transformer parameters"
)

class Transformer(Worker):
    """
    This is the main-thread part of the transformer
    """
    _required_code_type = PythonCell.CodeTypes.FUNCTION
    transformer = None
    transformer_thread = None
    output_thread = None
    active = False

    def __init__(self, transformer_params):
        from .context import get_active_context
        super().__init__()
        self.state = {}
        self.code = InputPin(self, "code", ("text", "code", "python"))
        thread_inputs = {}
        self._io_attrs = ["code"]
        self._pins = {"code":self.code}
        self._output_name = None
        self._connected_output = False
        self._last_value = None
        self._message_id = 0
        _registrars = []
        self._transformer_params = OrderedDict()
        for p in sorted(transformer_params.keys()):
            param = transformer_params[p]
            self._transformer_params[p] = param
            pin = None
            dtype = param.get("dtype", None)
            if isinstance(dtype, list):
                dtype = tuple(dtype)
            if param["pin"] == "input":
                pin = InputPin(self, p, dtype)
                thread_inputs[p] = dtype
            elif param["pin"] == "output":
                pin = OutputPin(self, p, dtype)
                assert self._output_name is None  # can have only one output
                self._output_name = p
            elif param["pin"] == "registrar":
                registrar_name = param["registrar"]
                ctx = get_active_context()
                manager = ctx._manager
                registrar = getattr(ctx.registrar, registrar_name)
                _registrars.append((registrar, p))
            else:
                raise ValueError(param["pin"])

            if pin is not None:
                self._io_attrs.append(p)
                self._pins[p] = pin

        """Output listener thread
        - It must have the same memory space as the main thread
        - It must run async from the main thread
        => This will always be a thread, regardless of implementation
        """
        self.output_finish = threading.Event()
        self.output_queue = deque()
        self.output_semaphore = threading.Semaphore(0)

        """Transformer thread
        For now, it is implemented as a thread
         However, it could as well be implemented as process
        - It shares no memory space with the main thread
          (other than the deques and semaphores, which could as well be
           implemented using network sockets)
        - It must run async from the main thread
        TODO: in case of process, synchronize registrars (use execnet?)
        """

        self.transformer = KernelTransformer(
            self,
            thread_inputs, self._output_name,
            self.output_queue, self.output_semaphore
        )
        if self.context is not None:
            self._set_context(self.context, self.name) #to update the transformer registrars

        for registrar, p in _registrars:
            registrar.connect(p, self)

        from .macro import add_activate
        add_activate(self)

    def activate(self):
        if self.active:
            return

        thread = threading.Thread(target=self.listen_output, daemon=True)
        self.output_thread = thread
        self.output_thread.start()

        thread = threading.Thread(target=self.transformer.run, daemon=True)
        self.transformer_thread = thread
        self.transformer_thread.start()

        self.active = True

    @property
    def transformer_params(self):
        return self._transformer_params

    def set_context(self, context):
        Worker.set_context(self, context)
        for p in self._pins:
            self._pins[p].set_context(context)
        return self

    def receive_update(self, input_pin, value, resource_name):
        self._message_id += 1
        self._pending_updates += 1
        msg = (self._message_id, input_pin, value, resource_name)
        self.transformer.input_queue.append(msg)
        self.transformer.semaphore.release()

    def receive_registrar_update(self, registrar_name, key, namespace_name):
        #TODO: this will only work for same-namespace (thread) kernels
        self._message_id += 1
        self._pending_updates += 1
        value = registrar_name, key, namespace_name
        self.transformer.input_queue.append((self._message_id, "@REGISTRAR", value, None))
        self.transformer.semaphore.release()

    def listen_output(self):
        # TODO logging
        # TODO requires_function cleanup

        # This code is very convoluted... networking expert wanted for cleanup!

        def get_item():
            self.output_semaphore.acquire()
            if self.output_finish.is_set():
                if not self.output_queue:
                    return
            output_name, output_value = self.output_queue.popleft()
            return output_name, output_value

        updates_on_hold = 0
        while True:
            try:
                if updates_on_hold:
                    """
                    Difficult situation. At the one hand, we can't hold on to
                    these processed updates forever:
                     It would keep the transformer marked as unstable, blocking
                      equilibrate().
                    On the other hand, an output_value could be just waiting
                    for us. If we decrement _pending_updates too early, this may
                    unblock equilibrate() while equilibrium has not been reached
                    The solution is that the kernel must respond within 500 ms
                    with an @START signal, and then a @END signal when the
                    computation is complete, then within 500 ms with the value
                    """
                    for n in range(100): #100x5 ms
                        ok = self.output_semaphore.acquire(blocking=False)
                        if ok:
                            self.output_semaphore.release()
                            break
                        time.sleep(0.005)
                    else:
                        self._pending_updates -= updates_on_hold
                        updates_on_hold = 0

                item = get_item()
                if item is None:
                    break
                output_name, output_value = item
                if output_name == "@START":
                    item = get_item()
                    if item is None:
                        break
                    output_name, output_value = item
                    assert output_name == "@END"
                    if updates_on_hold:
                        for n in range(100): #100x5 ms
                            ok = self.output_semaphore.acquire(blocking=False)
                            if ok:
                                self.output_semaphore.release()
                                break
                            time.sleep(0.005)
                        else:
                            self._pending_updates -= updates_on_hold
                            updates_on_hold = 0
                    item = get_item()
                    if item is None:
                        break
                    output_name, output_value = item

                if output_name is None and output_value is not None:
                    updates_processed = output_value[0]
                    if self._pending_updates < updates_processed:
                        #This will not set the worker as stable
                        self._pending_updates -= updates_processed
                    else:
                        # hold on to updates_processed for a while, we don't
                        #  want to set the worker as stable before we have
                        #  done a send_update
                        updates_on_hold += updates_processed
                    continue

                assert output_name == self._output_name, item
                if self._connected_output:
                    self._pins[self._output_name].send_update(output_value)
                else:
                    self._last_value = output_value

                item = get_item()
                if item is None:
                    break
                output_name, output_value = item
                assert output_name is None
                updates_processed = output_value[0]
                self._pending_updates -= updates_processed

                if updates_on_hold:
                    self._pending_updates -= updates_on_hold
                    updates_on_hold = 0
            except:
                traceback.print_exc() #TODO: store it?

    def _on_connect_output(self):
        last_value = self._last_value
        if last_value is not None:
            self._last_value = None
            self._pins[self._output_name].send_update(last_value)
        self._connected_output = True

    def _on_disconnect_output(self):
        if self._destroyed:
            return
        self._connected_output = False

    def destroy(self):
        if self._destroyed:
            return

        # gracefully terminate the transformer thread
        if self.transformer_thread is not None:
            self.transformer.finish.set()
            self.transformer.semaphore.release() # to unblock the .finish event
            self.transformer.finished.wait()
            self.transformer_thread.join()
            del self.transformer_thread
            self.transformer_thread = None

        # gracefully terminate the output thread
        if self.output_thread is not None:
            self.output_finish.set()
            self.output_semaphore.release() # to unblock for the output_finish
            self.output_thread.join()
            del self.output_thread
            self.output_thread = None

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

    def __dir__(self):
        return object.__dir__(self) + list(self._pins.keys())

    def _set_context(self, context, name, force_detach=False):
        super()._set_context(context, name, force_detach)
        if self.transformer is None:
            return
        if self.context is not None:
            self.transformer.registrars = self.context.registrar
        else:
            self.transformer.registrars = None

# @macro takes nothing, a type, or a dict of types
@macro(type=("json", "seamless", "transformer_params"), with_context=False)
def transformer(kwargs):
    from seamless.core.transformer import Transformer #code must be standalone
    #TODO: remapping, e.g. output_finish, destroy, ...
    return Transformer(kwargs)

from .context import Context
