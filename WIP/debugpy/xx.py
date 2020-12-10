import debugpy
debugpy.listen(("localhost", 5678))  # listen for incoming DAP client connections
debugpy.wait_for_client()  # wait for a client to connect

code = open("yy.py").read()
from seamless.core.cached_compile import cached_compile
obj = cached_compile(code, "yy.py")
exec(obj)
