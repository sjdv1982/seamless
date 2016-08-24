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
  doc="Transformer parameters"
)


class Editor(Process):
    """
    This is the main-thread part of the process
    """
    _required_code_type = PythonCell.CodeTypes.BLOCK

    def __init__(self, editor_params):
        code_input_names = "code_start", "code_update", "code_stop"
        mandatory_params = dict((name, {"pin": "input", "dtype": ("text", "code", "python")})
                                for name in code_input_names)
        all_params = editor_params.copy()
        all_params.update(mandatory_params)

        super().__init__(all_params)

        self.state = {}

        kernel_inputs = {name: param['dtype'] for name, param in editor_params.items() if param["pin"] == "input"}
        self.editor = KernelEditor(self, kernel_inputs, self.output_names)

    def _create_output_pin(self, name, dtype):
        return EditorOutputPin(self, name, dtype)

    def output_update(self, name, value):
        self._pins[name].update(value)

    def receive_update(self, input_pin, value):
        f = self.editor.process_input
        work = partial(f, input_pin, value)
        seamless.add_work(work)

    def destroy(self):
        self._code_stop()

        super(Editor, self).destroy()


# @macro takes nothing, a type, or a dict of types
@macro(("json", "seamless", "transformerparams"))
def editor(kwargs):
    # TODO: remapping, e.g. output_finish, destroy, ...
    return Editor(kwargs)

from .context import Context
