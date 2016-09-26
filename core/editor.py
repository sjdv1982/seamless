#totally synchronous, for GUI
#TODO: make an async version too (see editor-OLD)

import traceback
from functools import partial

from .macro import macro
from .process import Process, InputPin, EditorOutputPin
from .cell import Cell, PythonCell
from .pysynckernel import Editor as KernelEditor
from ..dtypes.objects import PythonBlockObject

from .. import dtypes
from .. import silk
import seamless

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
    _required_code_type = PythonCell.CodeTypes.ANY

    def __init__(self, editor_params):
        self.state = {}
        self.output_names = []
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
        for p in editor_params:
            param = editor_params[p]
            if param["pin"] == "input":
                pin = InputPin(self, p, param["dtype"])
                kernel_inputs[p] = param["dtype"]
            elif param["pin"] == "output":
                pin = EditorOutputPin(self, p, param["dtype"])
                self.output_names.append(p)
            self._io_attrs.append(p)
            self._pins[p] = pin


        self.editor = KernelEditor(
            self,
            kernel_inputs,
            self.output_names,
        )

    def output_update(self, name, value):
        self._pins[name].update(value)

    def __getattr__(self, attr):
        if attr not in self._pins:
            raise AttributeError(attr)
        else:
            return self._pins[attr]

    def set_context(self, context):
        Process.set_context(self, context)
        for p in self._pins:
            self._pins[p].set_context(context)
        return self

    def receive_update(self, input_pin, value):
        f = self.editor.process_input
        work = partial(f, input_pin, value)
        seamless.add_work(work)



    def destroy(self):
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
@macro(("json", "seamless", "transformerparams"))
def editor(kwargs):
    #TODO: remapping, e.g. output_finish, destroy, ...
    return Editor(kwargs)

from .context import Context
