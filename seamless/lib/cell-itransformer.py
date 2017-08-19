from seamless.gui.shell import MyInProcessKernelManager
kernel_manager = MyInProcessKernelManager()
kernel_manager.start_kernel(globals())

params = PINS.transformer_params.get()
inp_names = [p for p,pin in params.items() if pin["pin"] == "input"]
outp_name = [p for p,pin in params.items() if pin["pin"] == "output"][0]


namespace = {}
exec("""
def last_cell():
    import inspect
    frame = inspect.currentframe()
    while "_" not in frame.f_globals:
        frame = frame.f_back
    _ = frame.f_globals["_"]
    if _ is None:
        return None
    elif isinstance(_, str):
        return _
    else:
        return _.data
""", namespace)
namespace0 = namespace.copy()

import json, inspect
from IPython.core.inputsplitter import IPythonInputSplitter

def execute(code):
    isp = IPythonInputSplitter()

    def do_execute():
        result = kernel.shell.run_cell(cell, False)
        if result.error_before_exec is not None:
            err = result.error_before_exec
        else:
            err = result.error_in_exec
        if not result.success:
            for tb in kernel.shell._last_traceback:
                print(tb)
            return False
        return True

    for line in code.splitlines():
        if isp.push_accepts_more():
            isp.push(line.strip("\n"))
            continue
        cell = isp.source_reset()
        if not do_execute():
            return False
        isp.push(line.strip("\n"))
    cell = isp.source_reset()
    if len(cell):
        return do_execute()
    else:
        return True

def compile_code():
    global kernel, code_expression, namespace
    namespace = namespace0.copy()
    kernel_manager.start_kernel(namespace)
    kernel = kernel_manager.kernel
    code = PINS.code.get()
    namespace["code"] = code
    result = execute(code)
    ok = False
    if result:
        ok = True
        if "transform" not in namespace:
            ok = False
        else:
            tf = namespace["transform"]
            if not callable(tf):
                ok = False
            try:
                signature = inspect.signature(tf)
            except ValueError:
                signature = None #built-in?
            if signature is not None:
                try:
                    signature.bind()
                except TypeError:
                    ok = False
    if not ok:
        raise Exception("Code must create a function 'transform' that can be invoked with zero arguments")

    for name in inp_names:
        pin = getattr(PINS, name)
        if pin.defined:
            namespace[name] = pin.get()

def run():
    namespace["_"] = None
    result = eval("transform()", namespace)
    if "html" not in params and "html" in namespace:
        PINS.html.set(namespace["html"])
    getattr(PINS, outp_name).set(result)

def do_update():
    if PINS.code.updated:
        compile_code()
    else:
        for name in inp_names:
            pin = getattr(PINS, name)
            if pin.updated:
                namespace[name] = pin.get()
    run()
