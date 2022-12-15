import sys
IPythonInputSplitter = None
MyInProcessKernelManager = None
def _imp():
    global IPythonInputSplitter, MyInProcessKernelManager
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
    """Executes Python code in an IPython kernel

    If the code is in IPython format (i.e. with % and %% magics),
     run it through ipython2python first
    """
    if MyInProcessKernelManager is None:
        _imp()
    kernel_manager = MyInProcessKernelManager()
    kernel_manager.start_kernel(namespace)
    kernel = kernel_manager.kernel

    result = kernel.shell.run_cell(code, False)
    if result.error_before_exec is not None:
        print(result.error_before_exec, file=sys.stderr)
    if result.error_in_exec is not None:
        print(result.error_in_exec, file=sys.stderr)
    if not result.success:
        if kernel.shell._last_traceback:
            for tb in kernel.shell._last_traceback:
                print(tb) #TODO: log
    return namespace

def ipython2python(code):
    if IPythonInputSplitter is None:
        _imp()
    isp = IPythonInputSplitter()
    newcode = ""
    for line in code.splitlines():
        if isp.push_accepts_more():
            isp.push(line.strip("\n"))
            continue
        cell = isp.source_reset()
        if cell.startswith("get_ipython().run_"):
            cell = "_ = " + cell
        newcode += cell + "\n"
        isp.push(line.strip("\n"))
    cell = isp.source_reset()
    if len(cell):
        if cell.startswith("get_ipython().run_"):
            cell = "_ = " + cell
        newcode += cell
    return newcode