import os,shutil
import tempfile
import numpy as np
import tarfile
import json
import sys
from io import BytesIO
from seamless.silk import Silk
from seamless.mixed.get_form import get_form
from seamless import subprocess
from subprocess import PIPE
env = os.environ.copy()

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
    tempdir = tempfile.mkdtemp(prefix="seamless-bash-transformer")
    os.chdir(tempdir)
    for pin in pins:
        v = globals()[pin]
        if isinstance(v, Silk):
            v = v.data
        storage, form = get_form(v)
        if storage.startswith("mixed"):
            raise TypeError("pin '%s' has mixed data" % pin)
        if storage == "pure-plain":
            if isinstance(form, str):
                vv = str(v)
                if len(vv) <= 1000:
                    env[pin] = vv                
            else:
                vv = json.dumps(v)
            with open(pin, "w") as pinf:
                pinf.write(vv)
        else: 
            if v.dtype == np.uint8 and v.ndim == 1:
                vv = v.tobytes()
                with open(pin, "bw") as pinf:
                    pinf.write(vv)
            else:           
                with open(pin, "bw") as pinf:
                    np.save(pinf,v,allow_pickle=False)
    process = subprocess.run(
      bashcode, capture_output=True, shell=True, check=True,
      env=env
    )
    stderr = process.stderr.decode()
    if len(stderr):
        print(stderr, file=sys.stderr)
    stdout = BytesIO(process.stdout)
    try:        
        tar = tarfile.open(fileobj=stdout)
        result = {}
        for member in tar.getnames():
            data = tar.extractfile(member).read()
            rdata = read_data(data)
            result[member] = rdata
    except (ValueError, tarfile.CompressionError, tarfile.ReadError):
        result = read_data(process.stdout)
finally:
    os.chdir(old_cwd)
    shutil.rmtree(tempdir, ignore_errors=True)
