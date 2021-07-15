"""No bug report needed... Seamless was not working because of source maps: make sure that *values* don't match!"""

FORK = True # Fork the Python process before attach
RENAME="-renamed"

import os, sys, json, signal, time
HOSTCWD = os.environ["HOSTCWD"] # Defined in the Docker run command
DOCKER_IMAGE = sys.argv[1]  # read from stdin via the Docker run command
HOST_SEP = "\\" if HOSTCWD.find("\\") > -1 else "/"
TEMPDIR="/tmp/12345678901234567890123456789012345678901234567890/SEAMLESS_5a9b340ddd8948f0ca5885d5647bd18d333398d3c0d32e00fb47c3940f01c1d4_module"
if not os.path.exists(TEMPDIR):
    os.makedirs(TEMPDIR)

cpp_code = """extern "C" int transform(int a, int b) {
    return a + b + 1000;
}"""

with open("transformation.cpp", "w") as f:
    f.write(cpp_code)

try:
    os.mkdir(".vscode")
except FileExistsError:
    pass

cwd = os.getcwd()
os.system("cp transformation.cpp {TEMPDIR}/transformation{RENAME}.cpp".format(TEMPDIR=TEMPDIR, RENAME=RENAME))
os.system("g++ -c -fPIC -g -O0 -fno-inline -Wall -o {TEMPDIR}/transformation{RENAME}.o {TEMPDIR}/transformation{RENAME}.cpp".format(TEMPDIR=TEMPDIR, RENAME=RENAME))
os.system("g++ -shared -fPIC -g3 -O0 -fno-inline -Wall  {TEMPDIR}/transformation{RENAME}.o -o transformation.so".format(TEMPDIR=TEMPDIR, RENAME=RENAME))

launch_json = {
    "configurations": [{
        "name": "debug transformation.cpp",
        "type": "cppdbg",
        "request": "attach",
        "program": "/opt/conda/bin/python",
        "pipeTransport": {
            "debuggerPath": "/usr/bin/gdb",
            "pipeProgram": "docker",
            "pipeArgs": ["exec", "-u", "root", "--privileged", "-i", DOCKER_IMAGE, "sh", "-c"],
            "pipeCwd": ""
        },
        "sourceFileMap": {
            "nonsense": HOSTCWD,
            TEMPDIR + "/transformation"+RENAME+".cpp":HOSTCWD + HOST_SEP + "transformation.cpp",
        },
        "MIMode": "gdb",
        "setupCommands": [
            {
                "description": "Enable pretty-printing for gdb",
                "text": "-enable-pretty-printing",
                "ignoreFailures": True
            },
        ]
    }]
}

"""
import ctypes
lib = ctypes.CDLL(os.path.abspath("./transformation.so"))    
"""

import cffi
ffibuilder = cffi.FFI()
ffibuilder.set_source(
    "_transformation", 
    "", 
    extra_objects=["{TEMPDIR}/transformation{RENAME}.o".format(TEMPDIR=TEMPDIR,RENAME=RENAME)]
)
ffibuilder.cdef("int transform(int a, int b);")
ffibuilder.compile(verbose=True)
from _transformation import lib

def run():
    launch_json["configurations"][0]["processId"] = os.getpid()
    with open(".vscode/launch.json", "w") as f:
        json.dump(launch_json, f, indent=4)
    
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