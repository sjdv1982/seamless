#totally synchronous, for GUI
#TODO: make an async version too (see editor-OLD)

import os
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
            #TODO: check that they don't overlap with editor attributes (.path, .name, ...),
            #     ...and with code_start, code_update, code_stop, or is that allowed  (???)
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
            func = self._code_stop
        except AttributeError:
            pass
        else:
            self._code_stop()

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
    #TODO: remapping, e.g. output_finish, destroy, ...
    return Editor(kwargs)

from .context import Context
