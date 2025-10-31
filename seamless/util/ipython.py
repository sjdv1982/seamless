"""Tools for interfacing with IPython"""

import sys

IPythonInputSplitter = None
MyInProcessKernelManager = None  # type: ignore


def _imp():
    global IPythonInputSplitter, MyInProcessKernelManager
    from IPython.core.inputsplitter import (  # pylint: disable=redefined-outer-name,no-name-in-module # type: ignore
        IPythonInputSplitter,
    )
    from ipykernel.inprocess.ipkernel import InProcessKernel  # type: ignore
    from ipykernel.inprocess.manager import InProcessKernelManager  # type: ignore
    from ipykernel.zmqshell import ZMQInteractiveShell  # type: ignore

    class MyInProcessKernel(InProcessKernel):
        """Replacement for IPython's InProcessKernel"""

        # get rid of singleton shell instance!
        class dummy:
            """Dummy interactive shell class that is not a singleton"""

            def instance(self, *args, **kwargs):
                """Get instance, but not singleton"""
                shell = ZMQInteractiveShell(*args, **kwargs)
                return shell

        shell_class = dummy()

    class MyInProcessKernelManager(  # pylint: disable=unused-variable
        InProcessKernelManager
    ):  # pylint: disable=redefined-outer-name
        """Replacement for IPython's InProcessKernelManager"""

        def start_kernel(self, namespace):  # pylint: disable=arguments-differ
            """Start kernel"""
            self.kernel = (  # pylint: disable=attribute-defined-outside-init
                MyInProcessKernel(
                    parent=self,
                    session=self.session,
                    user_ns=namespace,
                )
            )


def execute(code, namespace):
    """Executes Python code in an IPython kernel

    If the code is in IPython format (i.e. with % and %% magics),
     run it through ipython2python first
    """
    if MyInProcessKernelManager is None:
        _imp()
    kernel_manager = MyInProcessKernelManager()  # pylint: disable=not-callable
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
                print(tb, file=sys.stderr)
    return namespace


def ipython2python(code):
    """Convert IPython code (including magics)to normal Python code"""
    if IPythonInputSplitter is None:
        _imp()
    isp = IPythonInputSplitter()  # type: ignore # pylint: disable=not-callable
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
