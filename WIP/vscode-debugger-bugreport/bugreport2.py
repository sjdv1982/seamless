"""No bug report needed"""

FORK = False # Fork the Python process before attach
GCC_SOURCE_MAP = False 

import os, sys, json, signal, time
HOSTCWD = os.environ["HOSTCWD"] # Defined in the Docker run command
DOCKER_IMAGE = sys.argv[1]  # read from stdin via the Docker run command
HOST_SEP = "\\" if HOSTCWD.find("\\") > -1 else "/"

cpp_code = """extern "C" int transform(int a, int b) {
    return a + b + 1000;
}"""

with open("transformation.cpp", "w") as f:
    f.write(cpp_code)

cwd = os.getcwd()
os.system("g++ -c -fPIC -g3 -O0 -fno-inline -Wall -o transformation.o transformation.cpp")
os.chdir(cwd)


def run():

    """
    import cffi
    ffibuilder = cffi.FFI()
    ffibuilder.set_source(
        "_transformation", 
        "", 
        extra_objects=["transformation.o"]
    )
    ffibuilder.cdef("int transform(int a, int b);")
    ffibuilder.compile(verbose=True)
    from _transformation import lib
    """
    os.system("g++ -shared -fPIC -g3 -O0 -fno-inline -Wall transformation.o -o transformation.so")

    import ctypes
    lib = ctypes.CDLL(os.path.abspath("./transformation.so"))

    result = lib.transform(10, 20)
    print("Transformation result", result)

    class DebuggerAttached(Exception):
        pass

    print("*" * 80)
    print("Process ID:", os.getpid())
    print("Waiting for VSCode debugger attach")
    print("Execution will pause until SIGUSR1 has been received")
    print("*" * 80)
    def handler(*args, **kwargs):
        raise DebuggerAttached
    signal.signal(signal.SIGUSR1, handler)
    try:
        time.sleep(3600)
    except DebuggerAttached:
        pass

    result = lib.transform(10, 20)
    print("Transformation result", result)

if FORK:
    import multiprocessing
    process = multiprocessing.Process(target=run)
    process.start()
    process.join()
else:
    run()