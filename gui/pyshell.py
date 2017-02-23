from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import QtInProcessKernelManager
from ipykernel.inprocess.ipkernel import InProcessKernel
from ipykernel.zmqshell import ZMQInteractiveShell

class MyInProcessKernel(InProcessKernel):
    #get rid of singleton shell instance!
    class dummy:
        def instance(self, *args, **kwargs):
            return(ZMQInteractiveShell(*args, **kwargs))
    shell_class = dummy()

class MyInProcessKernelManager(QtInProcessKernelManager):
    def start_kernel(self, namespace):
        self.kernel = MyInProcessKernel(parent=self, session=self.session, user_ns = namespace)

class PyShell:
    _dummy = False
    def __init__(self, namespace):
        from .. import qt_error
        if qt_error is not None:
            self._dummy = True
            return
        self.namespace = namespace
        self.kernel_manager = MyInProcessKernelManager()
        self.kernel_manager.start_kernel(namespace)
        self.kernel_client = self.kernel_manager.client()
        self.kernel_client.start_channels()
        control = RichJupyterWidget()
        self.control = control
        control.kernel_manager = self.kernel_manager
        control.kernel_client = self.kernel_client
        control.show()
    def stop():
        if self._dummy:
            return
        self.kernel_manager.client().stop_channels()
        self.kernel_manager.shutdown_kernel()
        self.control.destroy()
