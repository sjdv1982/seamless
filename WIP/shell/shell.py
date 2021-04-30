
class MyDict(dict):
    def __setitem__(self, attr, value):
        print("SET", attr, value)
        super().__setitem__(attr, value)

def start_shell():
    from ipykernel.kernelapp import IPKernelApp
    app = IPKernelApp.instance()
    app.initialize([])
    #app.kernel.user_module = module
    app.kernel.user_ns = MyDict(a=10)
    app.shell.set_completer_frame()
    app.start()

if __name__ == "__main__":
    start_shell()