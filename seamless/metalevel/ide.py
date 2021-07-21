import json
import os
from copy import deepcopy
import traceback
from typing import OrderedDict
import commentjson

hostcwd = os.environ.get("HOSTCWD")
from .debugmode import docker_container

launch_json_py = {
    #"name": "Python: Remote Attach",
    "type": "python",
    "request": "attach",
    "connect": {
        "host": "localhost",
        #"port": 5678
    },
    "pathMappings": [
    ]
}

launch_json_compiled_docker =  {
    #"name": "ctx.tf: debug Seamless C/C++ transformer",
    "type": "cppdbg",
    "request": "attach",
    "program": "/opt/conda/bin/python",
    #"processId": "1114",
    "pipeTransport": {
        "debuggerPath": "/usr/bin/gdb",
        "pipeProgram": "docker",
        "pipeArgs": ["exec", "-u", "root", "--privileged", "-i", None, "sh", "-c"],
        "pipeCwd": ""
    },
    "sourceFileMap": OrderedDict(),
    "MIMode": "gdb",
    "setupCommands": [
        {
            "description": "Enable pretty-printing for gdb",
            "text": "-enable-pretty-printing",
            "ignoreFailures": True
        },
        {
            # NOT WORKING
            "text": "-interpreter-exec console \"skip -fi /build/glibc-eX1tMB/glibc-2.31/sysdeps/unix/sysv/linux/select.c\"" 
        }
    ]
}


def _vscode_init():
    curr_dir = "."
    if hostcwd is not None:
        curr_dir = "/cwd"
    vscode_dir = os.path.join(curr_dir, ".vscode")
    host_vscode_dir = os.path.abspath(vscode_dir)
    if hostcwd is not None:
        host_vscode_dir = os.path.join(hostcwd, ".vscode")
    if not os.path.exists(vscode_dir):
        print("{} does not exist, creating...".format(host_vscode_dir))
        os.mkdir(vscode_dir)
    launch_json = os.path.join(vscode_dir, "launch.json")
    if not os.path.exists(launch_json):
        host_launch_json = os.path.join(host_vscode_dir, "launch.json")
        print("{} does not exist, creating...".format(host_launch_json))
        with open(launch_json, "w") as f:
            json.dump({}, f)
        launch_json_data = {}
    else:
        with open(launch_json, "r") as f:
            data = f.read()
            try:
                launch_json_data = json.loads(data)
            except ValueError:
                launch_json_data = commentjson.loads(data)

    return launch_json, launch_json_data

def _vscode_py_attach_create(debug):
    launch_json, launch_json_data = _vscode_init()
    entry = deepcopy(launch_json_py)
    entry["name"] = debug["name"]
    entry["connect"]["port"] = int(debug["python_attach_port"])
    for source, target in debug.get("source_map", []):
        mapping = {
            "localRoot": target,
            "remoteRoot": source
        }
        entry["pathMappings"].append(mapping)
    if "configurations" not in launch_json_data:
        launch_json_data["configurations"] = []
    config = launch_json_data["configurations"]
    config[:] = [entry for entry in config if entry["name"] != name]
    config.append(entry)
    with open(launch_json, "w") as f:
        json.dump(launch_json_data, f, indent=4)

def _vscode_attach_cleanup(debug):
    try:
        launch_json, launch_json_data = _vscode_init()
    except Exception as exc:
        traceback.print_exc()
        raise exc from None
    name = debug["name"]
    if "configurations" not in launch_json_data:
        launch_json_data["configurations"] = []
    config = launch_json_data["configurations"]
    config[:] = [entry for entry in config if entry["name"] != name]
    print("Debugging of '{}' terminated".format(debug["name"]))
    with open(launch_json, "w") as f:
        json.dump(launch_json_data, f, indent=4)

def _vscode_compiled_attach_create(debug):
    from ..core.build_module import SEAMLESS_EXTENSION_DIR
    launch_json, launch_json_data = _vscode_init()
    if docker_container is None:
        raise NotImplementedError  # compiled debug outside Docker container
    name = debug["name"]
    entry = deepcopy(launch_json_compiled_docker)
    entry["name"] = name
    entry["processId"] = int(os.getpid())
    pipeargs = entry["pipeTransport"]["pipeArgs"]
    for n in range(len(pipeargs)):
        if pipeargs[n] is None:
            pipeargs[n] = docker_container
    main = debug["main-code"]
    main2 = os.path.splitext(main)[1]
    main3 = os.path.relpath(main, "/cwd")
    main3 = "${workspaceFolder}/" + main3
    key = SEAMLESS_EXTENSION_DIR + "/" + debug["full_module_names"]["module"] + "/main" + main2
    entry["sourceFileMap"][key] = main3
    for source, target in debug.get("source_map", []):
        entry["sourceFileMap"][source] = target
    if "configurations" not in launch_json_data:
        launch_json_data["configurations"] = []
    config = launch_json_data["configurations"]
    config[:] = [entry for entry in config if entry["name"] != name]
    config.append(entry)
    with open(launch_json, "w") as f:
        json.dump(launch_json_data, f, sort_keys=False,indent=4)



def debug_pre_hook(debug):
    if debug is None:
        return
    ide = debug["ide"]
    if debug.get("python_attach"):
        if ide != "vscode":
            raise NotImplementedError
        return _vscode_py_attach_create(debug)
    if debug.get("generic_attach"):
        return _vscode_compiled_attach_create(debug)

def debug_post_hook(debug):
    if debug is None:
        return
    ide = debug["ide"]
    if debug.get("python_attach"):
        if ide != "vscode":
            raise NotImplementedError
        return _vscode_attach_cleanup(debug)            
    if debug.get("generic_attach"):
        if ide != "vscode":
            raise NotImplementedError
        return _vscode_attach_cleanup(debug)