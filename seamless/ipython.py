from IPython.core.inputsplitter import IPythonInputSplitter
from ipykernel.inprocess.ipkernel import InProcessKernel
from ipykernel.inprocess.manager import InProcessKernelManager
from ipykernel.zmqshell import ZMQInteractiveShell

class MyInProcessKernel(InProcessKernel):
    #get rid of singleton shell instance!
    class dummy:
        def instance(self, *args, **kwargs):
            shell = ZMQInteractiveShell(*args, **kwargs)
            return shell
    shell_class = dummy()

class MyInProcessKernelManager(InProcessKernelManager):
    def start_kernel(self, namespace):
        self.kernel = MyInProcessKernel(parent=self, session=self.session, user_ns = namespace)

def execute(code, namespace):
    isp = IPythonInputSplitter()
    kernel_manager = MyInProcessKernelManager()
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
