# TODO: copy-pasted from transformer.py:
#  - common base class in process.py ??
#  - make *both* a front-end to process.py?
# decide after implementing effector.py!!

from collections import deque
from queue import Queue
import threading
import traceback

from .macro import macro
from .process import Process, InputPin, EditorOutputPin
from .cell import Cell, PythonCell
from .pythreadkernel import Editor as KernelEditor
from ..dtypes.objects import PythonBlockObject

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
silk.register(
  ###Cell.fromfile("transformer_param.silk"), #TODO
  doc = "Transformer pin parameters",
  docson = transformer_param_docson  #("json", "docson")
)

transformer_params = {
  "*": "silk.TransformerParam",
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
  ("json", "seamless", "transformerparams"),
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

class Editor(Process):
    """
    This is the main-thread part of the process
    """
    _required_code_type = PythonCell.CodeTypes.BLOCK

    def __init__(self, editor_params):
        self.state = {}
        self.namespace = {}
        self.output_names = []
        self.code_start = InputPin(self, "code_start", ("text", "code", "python"))
        self.code_update = InputPin(self, "code_update", ("text", "code", "python"))
        self.code_stop = InputPin(self, "code_stop", ("text", "code", "python"))
        self.code_start_block = None
        self.code_stop_block = None
        thread_inputs = {}
        self._io_attrs = ["code_start", "code_update", "code_stop"]
        self._pins = {
                        "code_start": self.code_start,
                        "code_update": self.code_update,
                        "code_stop": self.code_stop,
                     }
        for p in editor_params:
            param = editor_params[p]
            if param["pin"] == "input":
                pin = InputPin(self, p, param["dtype"])
                thread_inputs[p] = param["dtype"]
            elif param["pin"] == "output":
                pin = EditorOutputPin(self, p, param["dtype"])
                self.output_names.append(p)
            self._io_attrs.append(p)
            self._pins[p] = pin

        """Output listener thread
        - It must have the same memory space as the main thread
        - It must run async from the main thread
        => This will always be a thread, regardless of implementation
        """
        self._active = False
        self.output_finish = threading.Event()
        self.kernel_lock = threading.Lock()
        self.output_queue = deque()
        self.output_semaphore = threading.Semaphore(0)
        thread = threading.Thread(target=self.listen_output, daemon=True)
        self.output_thread = thread
        self.output_thread.start()

        """Editor thread
        For now, it is implemented as a thread
         However, it could as well be implemented as process
        - It shares no memory space with the main thread
          (other than the deques and semaphores, which could as well be
           implemented using network sockets)
        - It must run async from the main thread
        """
        self.kernel_inputs = {}
        inputs = self.kernel_inputs
        inputs["code_start"] = PythonBlockObject("code_start", ("text", "code", "python"))
        inputs["code_stop"] = PythonBlockObject("code_stop", ("text", "code", "python"))
        self.namespace.clear()
        self.namespace["_cache"] = {}
        self.editor = KernelEditor(
            self.namespace, thread_inputs,
            self.output_names, self.output_queue, self.output_semaphore,
            self.kernel_lock
        )
        self.editor_thread = threading.Thread(target=self.editor.run, daemon=True)
        self.editor_thread.start()

    def __getattr__(self, attr):
        if attr not in self._pins:
            raise AttributeError(attr)
        else:
            return self._pins[attr]

    def _code_stop(self):
        if self._active:
            exec(self.code_stop_block, self.namespace)
            self._active = False
            self.editor._set_namespace()

    def _code_start(self):
        assert not self._active
        exec(self.code_start_block, self.namespace)
        self._active = True

    def set_context(self, context):
        Process.set_context(self, context)
        for p in self._pins:
            self._pins[p].set_context(context)
        return self

    def receive_update(self, input_pin, value):
        with self.kernel_lock:
            try:
                # If any code object is updated, recompile
                if input_pin in ("code_start", "code_stop"):
                    data_object = self.kernel_inputs[input_pin]
                    data_object.parse(value)
                    data_object.validate()

                if input_pin == "code_stop":
                    self.code_stop_block = compile(value, self.editor.name + "_stop", "exec")
                    if self.code_start_block is not None and not self._active:
                        self._code_start()

                if input_pin == "code_start":
                    self.code_start_block = compile(value, self.editor.name + "_start", "exec")
                    if self.code_stop_block is not None:
                        self._code_stop()
                        self._code_start()

            except Exception as e:
                import traceback
                traceback.print_exc()
                return
        self.editor.input_queue.append((input_pin, value))
        self.editor.semaphore.release()

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
                self._pins[output_name].update(output_value)

            except:
                traceback.print_exc()  # TODO: store it?

    def destroy(self):
        # gracefully terminate the transformer thread
        if self.editor_thread is not None:
            self.editor.finish.set()
            self.editor.semaphore.release()  # to unblock the .finish event
            self.editor.finished.wait()
            self.editor_thread.join()
            del self.editor_thread
            self.editor_thread = None

        # gracefully terminate the output thread
        if self.output_thread is not None:
            self.output_finish.set()
            self.output_semaphore.release() # to unblock for the output_finish
            self.output_thread.join()
            del self.output_thread
            self.output_thread = None

        self._code_stop()

        # free all input and output pins
        for attr in self._io_attrs:
            value = getattr(self, attr)
            if value is None:
                continue

            setattr(self, attr, None)
            del value

    def __del__(self):
        try:
            self.destroy()

        except Exception as err:
            print(err)
            pass

# @macro takes nothing, a type, or a dict of types
@macro(type=("json", "seamless", "transformerparams"), with_context=False)
def editor(kwargs):
    from seamless.core.editor import Editor #code must be standalone
    #TODO: remapping, e.g. output_finish, destroy, ...
    return Editor(kwargs)

from .context import Context
