import os,shutil
import tempfile
import numpy as np
import tarfile
import json
import sys
from io import BytesIO
from seamless.silk import Silk
from seamless.core.transformation import SeamlessTransformationError
from seamless.mixed.get_form import get_form
from seamless import subprocess
from subprocess import PIPE
import psutil
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
try:
    process = None
    tempdir = tempfile.mkdtemp(prefix="seamless-bash-transformer")
    os.chdir(tempdir)
    signal.signal(signal.SIGTERM, sighandler)
    for pin in pins_:
        v = globals()[pin]
        if isinstance(v, Silk):
            v = v.unsilk
        storage, form = get_form(v)
        if storage.startswith("mixed"):
            raise TypeError("pin '%s' has mixed data" % pin)
        if storage == "pure-plain":
            if isinstance(form, str):
                vv = str(v)
                if not vv.endswith("\n"): vv += "\n"
                if len(vv) <= 1000:
                    env[pin] = vv
            else:
                vv = json.dumps(v)
            with open(pin, "w") as pinf:
                pinf.write(vv)
        elif isinstance(v, bytes):
            with open(pin, "bw") as pinf:
                pinf.write(v)
        else:
            if v.dtype == np.uint8 and v.ndim == 1:
                vv = v.tobytes()
                with open(pin, "bw") as pinf:
                    pinf.write(vv)
            else:
                with open(pin, "bw") as pinf:
                    np.save(pinf,v,allow_pickle=False)
    try:
        bash_header = """set -u -e -o pipefail
trap '' PIPE
trap 'jobs -p | xargs -r kill' EXIT
"""
        bashcode2 = bash_header + bashcode
        process = subprocess.run(
            bashcode2, capture_output=True, shell=True, check=True,
            executable='/bin/bash',
            env=env
        )
    except subprocess.CalledProcessError as exc:
        stdout = exc.stdout
        try:
            stdout = stdout.decode()
        except:
            pass
        stderr = exc.stderr
        try:
            stderr = stderr.decode()
        except:
            pass
        raise SeamlessTransformationError("""
Bash transformer exception
==========================

*************************************************
* Command
*************************************************
{}
*************************************************

*************************************************
* Standard output
*************************************************
{}
*************************************************

*************************************************
* Standard error
*************************************************
{}
*************************************************
""".format(bashcode, stdout, stderr)) from None
    if not os.path.exists(resultfile):
        msg = """
Bash transformer exception
==========================

*************************************************
* Command
*************************************************
{}
*************************************************
Error: Result file RESULT does not exist
""".format(bashcode)
        try:
            stdout = process.stdout.decode()
            if len(stdout):
                msg += """*************************************************
* Standard output
*************************************************
{}
*************************************************
""".format(stdout)
            stderr = process.stderr.decode()
            if len(stderr):
                msg += """*************************************************
* Standard error
*************************************************
{}
*************************************************
""".format(stderr)

        except:
            pass

        raise SeamlessTransformationError(msg)
    else:
        stdout = process.stdout
        try:
            stdout = stdout.decode()
        except:
            pass
        if len(stdout):
            print(stdout)

        stderr = process.stderr
        try:
            stderr = stderr.decode()
        except:
            pass
        if len(stderr):
            print(stderr, file=sys.stderr)

    try:
        tar = tarfile.open(resultfile)
        result = {}
        for member in tar.getnames():
            data = tar.extractfile(member).read()
            rdata = read_data(data)
            result[member] = rdata
    except (ValueError, tarfile.CompressionError, tarfile.ReadError):
        with open(resultfile, "rb") as f:
            resultdata = f.read()
        result = read_data(resultdata)
finally:
    os.chdir(old_cwd)
    shutil.rmtree(tempdir, ignore_errors=True)
