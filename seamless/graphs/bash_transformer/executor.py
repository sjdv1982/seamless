import os,shutil
import tempfile
import numpy as np
import json
from io import BytesIO
from silk import Silk
from seamless.core.transformation import SeamlessStreamTransformationError
from seamless.core.mount_directory import write_to_directory
from silk.mixed.get_form import get_form
from seamless import subprocess_ as subprocess
from subprocess import PIPE
import signal

env = os.environ.copy()

resultfile = "RESULT"

def sighandler(signal, frame):
    if process is not None:
        subprocess.kill_children(process)
    os.chdir(old_cwd)
    shutil.rmtree(tempdir, ignore_errors=True)
    raise SystemExit()

def read_data(data):
    if OUTPUTPIN[0] == "bytes" or OUTPUTPIN == ("mixed", {"*": "##"}):
        return data
    try:
        npdata = BytesIO(data)
        return np.load(npdata)
    except (ValueError, OSError):
        try:
            try:
                sdata = data.decode()
            except Exception:
                return np.frombuffer(data, dtype=np.uint8)
            return json.loads(sdata)
        except ValueError:
            return sdata

old_cwd = os.getcwd()

def _write_file(pinname, data, filemode):
    if pinname.startswith("/"):
        raise ValueError("Pin {}: Absolute path is not allowed")
    path_elements = pinname.split("/")
    if ".." in path_elements:
        raise ValueError("Pin {}: .. is not allowed")
    if len(path_elements) > 1:
        parent_dir = os.path.dirname(pinname)
        os.makedirs(parent_dir, exist_ok=True)       
    with open(pinname, filemode) as pinf:
        pinf.write(data)

try:
    process = None
    tempdir = tempfile.mkdtemp(prefix="seamless-bash-transformer")
    os.chdir(tempdir)
    signal.signal(signal.SIGTERM, sighandler)
    for pin in pins_:
        if pin == "pins_":
            continue
        if pin == "bashcode":
            continue
        v = PINS[pin]
        if isinstance(v, Silk):
            v = v.unsilk
        if pin in FILESYSTEM:
            if FILESYSTEM[pin]["filesystem"]:
                env[pin] = v
                pin_parent = os.path.dirname(pin)
                if len(pin_parent):
                    os.makedirs(pin_parent, exist_ok=True)
                os.symlink(v, pin)
                continue
            elif FILESYSTEM[pin]["mode"] == "directory":
                write_to_directory(pin, v, cleanup=False, deep=False, text_only=False)
                env[pin] = pin
                continue
        storage, form = get_form(v)
        if storage.startswith("mixed"):
            raise TypeError("pin '%s' has '%s' data" % (pin, storage))
        if storage == "pure-plain":
            if isinstance(form, str):
                vv = str(v)
                if not vv.endswith("\n"): vv += "\n"
                if pin.find(".") == -1 and len(vv) <= 1000:
                    env[pin] = vv.rstrip("\n")
            else:
                vv = json.dumps(v)
            _write_file(pin, vv, "w")
        elif isinstance(v, bytes):
            _write_file(pin, v, "bw")
        else:
            if v.dtype == np.uint8 and v.ndim == 1:
                vv = v.tobytes()
                with open(pin, "bw") as pinf:
                    pinf.write(vv)
            else:
                with open(pin, "bw") as pinf:
                    np.save(pinf,v,allow_pickle=False)
    bash_header = """set -u -e
trap 'jobs -p | xargs -r kill' EXIT
"""
    bashcode2 = bash_header + bashcode
    process = subprocess.Popen(            
        bashcode2, shell=True, 
        stdout = subprocess.PIPE,
        stderr = subprocess.STDOUT,
        executable='/bin/bash',
        env=env
    )
    for line in process.stdout:
        try:
            line = line.decode()
        except UnicodeDecodeError:
            pass
        print(line,end="")
    process.wait()

    if process.returncode:
        raise SeamlessStreamTransformationError("""
Bash transformer exception
==========================

Error: Return code {}

*************************************************
* Command
*************************************************
{}
*************************************************
""".format(process.returncode, bashcode)) from None
    if not os.path.exists(resultfile):
        msg = """
Bash transformer exception
==========================

Error: Result file/folder RESULT does not exist

*************************************************
* Command
*************************************************
{}
*************************************************
""".format(bashcode)
        raise SeamlessStreamTransformationError(msg)

    if os.path.isdir(resultfile):
        result0 = {}
        for dirpath, _, filenames in os.walk(resultfile):
            for filename in filenames:
                full_filename = os.path.join(dirpath, filename)
                assert full_filename.startswith(resultfile + "/")
                member = full_filename[len(resultfile) + 1:]
                data = open(full_filename, "rb").read()
                rdata = read_data(data)
                result0[member] = rdata
        result = {}
        for k in sorted(result0.keys()):
            result[k] = result0[k]
            del result0[k]
    else:
        with open(resultfile, "rb") as f:
            resultdata = f.read()
        result = read_data(resultdata)
finally:
    if process is not None:
        subprocess.kill_children(process)
    os.chdir(old_cwd)
    shutil.rmtree(tempdir, ignore_errors=True)
