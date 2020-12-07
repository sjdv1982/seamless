def start_shell():
    from ipykernel.kernelapp import IPKernelApp
    app = IPKernelApp.instance()
    app.initialize([])
    #app.kernel.user_module = module
    app.kernel.user_ns = {"a": 10}
    app.shell.set_completer_frame()
    app.start()

if __name__ == "__main__":
    start_shell()