#totally synchronous, for GUI
#TODO: make an async version too (see editor-OLD)

import os
import traceback
from functools import partial
from collections import OrderedDict

from .macro import macro
from .process import Process, InputPin, EditPin, OutputPin
from .cell import Cell, PythonCell
from .pysynckernel import Editor as KernelEditor
from ..dtypes.objects import PythonBlockObject

from .. import dtypes
from .. import silk
import seamless

#TODO: on_disconnect? don't do anything if self._destroyed

editor_param_docson = {} #TODO, adapt from transformer and from editor.silk
currdir = os.path.dirname(__file__)
silk.register(
  open(os.path.join(currdir, "editor.silk")).read(),
  doc = "Editor pin parameters",
  docson = editor_param_docson  #("json", "docson")
)

editor_params = {
  "*": "silk.EditorPin",
}
dtypes.register(
  ("json", "seamless", "editor_params"),
  typeschema = editor_params, #("json", "typeschema")
  docson = {
    "*": "Editor pin parameters",
  },
  doc = "Editor parameters"
)

class Editor(Process):
    """
    This is the main-thread part of the process
    """
    _required_code_type = PythonCell.CodeTypes.ANY

    def __init__(self, editor_params):
        super().__init__()
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
        self._editor_params = OrderedDict()
        for p in sorted(editor_params.keys()):
            #TODO: check that they don't overlap with editor attributes (.path, .name, ...),
            #     ...and with code_start, code_update, code_stop, or is that allowed  (???)
            param = editor_params[p]
            self._editor_params[p] = param
            dtype = param.get("dtype", None)
            if isinstance(dtype, list):
                dtype = tuple(dtype)
            if param["pin"] == "input":
                pin = InputPin(self, p, dtype)
                kernel_inputs[p] = dtype, True
            elif param["pin"] == "output":
                pin = OutputPin(self, p, dtype)
                self.outputs[p] = dtype
            elif param["pin"] == "edit":
                pin = EditPin(self, p, dtype)
                kernel_inputs[p] = dtype, param.get("must_be_defined", True)
                self.outputs[p] = dtype
            self._io_attrs.append(p)
            self._pins[p] = pin


        self.editor = KernelEditor(
            self,
            kernel_inputs,
            self.outputs,
        )
    @property
    def editor_params(self):
        return self._editor_params

    def output_update(self, name, value):
        self._pins[name].send_update(value)

    def set_context(self, context):
        Process.set_context(self, context)
        for p in self._pins:
            self._pins[p].set_context(context)
        return self

    def receive_update(self, input_pin, value):
        f = self.editor.process_input
        if self._pins[input_pin].dtype == "signal":
            f(input_pin, value)
        else:
            work = partial(f, input_pin, value)
            seamless.add_work(work)

    def receive_registrar_update(self, registrar_name, key, namespace_name):
        #TODO: this will only work for same-namespace (thread) kernels
        f = self.editor.process_input
        value = registrar_name, key, namespace_name
        work = partial(f, "@REGISTRAR", value)
        seamless.add_work(work, priority=True)

    def __dir__(self):
        return object.__dir__(self) + list(self._pins.keys())

    def destroy(self):
        if self._destroyed:
            return
        try:
            func = self.editor
        except AttributeError:
            pass
        else:
            self.editor.destroy()

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
@macro(type=("json", "seamless", "editor_params"),with_context=False)
def editor(kwargs):
    from seamless.core.editor import Editor #code must be standalone
    #TODO: remapping, e.g. output_finish, destroy, ...
    return Editor(kwargs)

from .context import Context
