from qtconsole.rich_jupyter_widget import RichJupyterWidget
from qtconsole.inprocess import InProcessKernelManager, QtInProcessKernelManager
from ipykernel.inprocess.ipkernel import InProcessKernel
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

class MyQtInProcessKernelManager(QtInProcessKernelManager):
    def start_kernel(self, namespace):
        self.kernel = MyInProcessKernel(parent=self, session=self.session, user_ns = namespace)

_shells = {}

class PyShell:
    _dummy = False
    def __init__(self, namespace, inputpin, windowtitle=None):
        assert isinstance(namespace, dict), namespace
        from . import qt_error
        if qt_error is not None:
            self._dummy = True
            return
        p = inputpin.path
        if p not in _shells:
            _shells[p] = []
        _shells[p].append(self)
        self.namespace = namespace
        self.inputpin = inputpin
        self.windowtitle = windowtitle
        self.kernel_manager = MyQtInProcessKernelManager()
        control = RichJupyterWidget()
        self.control = control
        control.kernel_manager = self.kernel_manager
        self.start()
    def start(self):
        if self._dummy:
            return
        self.kernel_manager.start_kernel(self.namespace)
        self.kernel_client = self.kernel_manager.client()
        self.kernel_client.start_channels()
        shell = self.kernel_manager.kernel.shell
        shell.events.register('post_run_cell', self._on_execute)
        self.control.kernel_client = self.kernel_client
        if self.windowtitle is not None:
            self.control.setWindowTitle(self.windowtitle)
        self.control.show()
    def _on_execute(self, result):
        text = result.info.raw_cell
        cell = self.inputpin.cell()
        #cell._shell_append(text)
    def stop(self):
        if self._dummy:
            return
        self.kernel_client.stop_channels()
        self.kernel_manager.shutdown_kernel()
        self.control.destroy()
    def reset(self, namespace, inputpin):
        self.stop()
        self.namespace = namespace
        self.inputpin = inputpin
        self.start()

def update_shells(inputpin, namespace):
    shells = _shells.get(inputpin.path, [])
    for shell in shells:
        shell.reset(namespace, inputpin)
