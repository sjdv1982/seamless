import json
import os
from copy import deepcopy
import traceback
import commentjson

hostcwd = os.environ.get("HOSTCWD")

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
    for source, target in debug["source_map"]:
        mapping = {
            "localRoot": "${workspaceFolder}" ,#+ target,
            "remoteRoot": source
        }
        entry["pathMappings"].append(mapping)
    if "configurations" not in launch_json_data:
        launch_json_data["configurations"] = []
    launch_json_data["configurations"].append(entry)
    with open(launch_json, "w") as f:
        json.dump(launch_json_data, f, indent=4)

def _vscode_py_attach_cleanup(debug):
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

def debug_pre_hook(debug):
    if debug is None:
        return
    ide = debug["ide"]
    if debug.get("python_attach"):
        if ide != "vscode":
            raise NotImplementedError
        return _vscode_py_attach_create(debug)            
    if debug.get("generic_attach"):
        raise NotImplementedError        

def debug_post_hook(debug):
    if debug is None:
        return
    ide = debug["ide"]
    if debug.get("python_attach"):
        if ide != "vscode":
            raise NotImplementedError
        return _vscode_py_attach_cleanup(debug)            
    if debug.get("generic_attach"):
        raise NotImplementedError                