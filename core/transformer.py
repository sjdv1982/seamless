from collections import deque, OrderedDict
import threading
import traceback
import os

from .macro import macro
from .process import Process, InputPin, OutputPin
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

class Transformer(Process):
    """
    This is the main-thread part of the transformer
    """
    _required_code_type = PythonCell.CodeTypes.FUNCTION
    transformer = None

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
            if param["pin"] == "input":
                pin = InputPin(self, p, param["dtype"])
                thread_inputs[p] = param["dtype"]
            elif param["pin"] == "output":
                pin = OutputPin(self, p, param["dtype"])
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
        thread = threading.Thread(target=self.listen_output, daemon=True)
        self.output_thread = thread
        self.output_thread.start()

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
            thread_inputs, self._output_name,
            self.output_queue, self.output_semaphore
        )
        self._set_context(self.context, self.name) #to update the transformer registrars

        for registrar, p in _registrars:
            registrar.connect(p, self)

        self.transformer_thread = threading.Thread(target=self.transformer.run, daemon=True)
        self.transformer_thread.start()

    @property
    def transformer_params(self):
        return self._transformer_params

    def set_context(self, context):
        Process.set_context(self, context)
        for p in self._pins:
            self._pins[p].set_context(context)
        return self

    def receive_update(self, input_pin, value):
        self._message_id += 1
        self.transformer.input_queue.append((self._message_id, input_pin, value))
        self.transformer.semaphore.release()

    def receive_registrar_update(self, registrar_name, key, namespace_name):
        #TODO: this will only work for same-namespace (thread) kernels
        self._message_id += 1
        value = registrar_name, key, namespace_name
        self.transformer.input_queue.append((self._message_id, "@REGISTRAR", value))
        self.transformer.semaphore.release()

    def listen_output(self):
        # TODO logging
        # TODO requires_function cleanup

        while True:
            try:
                self.output_semaphore.acquire()
                if self.output_finish.is_set():
                    if not self.output_queue:
                        break

                output_name, output_value = self.output_queue.popleft()
                assert output_name == self._output_name
                if self._connected_output:
                    self._pins[self._output_name].send_update(output_value)
                else:
                    self._last_value = output_value

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
