from ...gui.shell import MyInProcessKernelManager
from . import RegistrarObject, BaseRegistrar
from IPython.core.inputsplitter import IPythonInputSplitter

def ipython_execute(code, title):
    #TODO: use title
    isp = IPythonInputSplitter()
    kernel_manager = MyInProcessKernelManager()
    namespace = {}
    kernel_manager.start_kernel(namespace)
    kernel = kernel_manager.kernel

    def do_execute():
        result = kernel.shell.run_cell(cell, False)
        if result.error_before_exec is not None:
            err = result.error_before_exec
        else:
            err = result.error_in_exec
        if not result.success:
            if kernel.shell._last_traceback:
                for tb in kernel.shell._last_traceback:
                    print(tb) #TODO: log

    for line in code.splitlines():
        if isp.push_accepts_more():
            isp.push(line.strip("\n"))
            continue
        cell = isp.source_reset()
        do_execute()
        isp.push(line.strip("\n"))
    cell = isp.source_reset()
    if len(cell):
        do_execute()
    return namespace

class IPythonRegistrarObject(RegistrarObject):

    def unregister(self):
        namespace = self.registrar._namespace
        for t in self.registered:
            if t in namespace:
                del namespace[t]
        self.registrar._unregister(self.context, self.data, self.data_name)

    def re_register(self, ipythoncode):
        context = self.context
        if context is None:
            return self
        self.unregister()
        title = self.data_name
        if title is None:
            title = "<string>"

        namespace = ipython_execute(ipythoncode, title)
        registered_types = [v for v in namespace if not v.startswith("_")]
        updated_keys = [k for k in registered_types]
        deleted_keys = [k for k in self.registered if k not in updated_keys]
        self.data = ipythoncode
        self.registered = registered_types
        self.registrar._namespace.update({k:namespace[k] for k in updated_keys})
        for k in deleted_keys:
            if k in self.registrar._namespace:
                del self.registrar._namespace[k]
        self.registrar.update(context, updated_keys+deleted_keys)
        super().re_register(ipythoncode)
        return self

class IPythonRegistrar(BaseRegistrar):
    _register_type = ("text", "code", "python")
    _registrar_object_class = IPythonRegistrarObject

    def __init__(self, namespace):
        self._namespace = namespace
        BaseRegistrar.__init__(self)

    #@macro(type=("text", "code", "ipython"), with_context=False,_registrar=True)
    def register(self, ipythoncode, name=None):
        self._register(ipythoncode, name)
        variables_old = list(self._namespace.keys())
        title = name
        if title is None:
            title = "<string>"

        namespace = ipython_execute(ipythoncode, title)
        registered_types = [v for v in namespace if not v.startswith("_")]
        self._namespace.update({k:namespace[k] for k in registered_types})
        return self._registrar_object_class(self, registered_types, ipythoncode, name)

    def get(self, key):
        return self._namespace[key]
