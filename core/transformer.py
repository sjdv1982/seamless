from collections import deque
import threading
from logging import getLogger

from .macro import macro
from .process import Process, InputPin, OutputPin
from .cell import Cell, PythonCell
from .pythreadkernel import Transformer as KernelTransformer

from .. import dtypes
from .. import silk

logger = getLogger(__name__)


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


# DUPLICATE
class Transformer(Process):
    """
    This is the main-thread part of the controller
    """
    _required_code_type = PythonCell.CodeTypes.FUNCTION

    def __init__(self, transformer_params):
        all_params = transformer_params.copy()
        all_params['code'] = {"pin": "input", "dtype": ("text", "code", "python")}

        super().__init__(all_params)

        self.state = {}

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
        """
        thread_inputs = {name: param['dtype'] for name, param in transformer_params.items() if param["pin"] == "input"}
        output_name = next(iter(self.output_names))
        self.transformer = KernelTransformer(thread_inputs, output_name, self.output_queue, self.output_semaphore)

        self.transformer_thread = threading.Thread(target=self.transformer.run, daemon=True)
        self.transformer_thread.start()

    def _create_output_pin(self, name, dtype):
        assert not self.output_names # can have only one output
        return OutputPin(self, name, dtype)

    def receive_update(self, input_pin, value):
        self.transformer.input_queue.append((input_pin, value))
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
                self._name_to_pin[output_name].update(output_value)

            except:
                logger.exception("An error occurred whilst waiting for an output value")

    def destroy(self):
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

        super(Transformer, self).destroy()


# @macro takes nothing, a type, or a dict of types
@macro(("json", "seamless", "transformerparams"))
def transformer(kwargs):
    # TODO: remapping, e.g. output_finish, destroy, ...
    return Transformer(kwargs)
