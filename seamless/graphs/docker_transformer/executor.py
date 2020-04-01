import os,shutil
import tempfile
import numpy as np
import tarfile
import json
import sys
from io import BytesIO
from seamless.silk import Silk
from seamless.mixed.get_form import get_form

def read_data(data):
    try:
        bdata = BytesIO(data)
        return np.load(bdata)
    except (ValueError, OSError):
        try:
            bdata = data.decode()
            return json.loads(bdata)
        except ValueError:
            return bdata

old_cwd = os.getcwd()
try:
    import docker as docker_module
    tempdir = tempfile.mkdtemp(prefix="seamless-docker-transformer")
    os.chdir(tempdir)
    options = docker_options.copy()
    if "environment" in options:
        env = options["environment"].copy()
    else:
        env = {}
    options["environment"] = env
    for pin in pins_:
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
            with open(pin, "bw") as pinf:
                np.save(pinf,vv,allow_pickle=False)
    docker_client = docker_module.from_env()
    options["remove"] = True
    if "volumes" not in options:
        options["volumes"] = {}
    volumes = options["volumes"]
    volumes[tempdir] = {"bind": "/run", "mode": "rw"}
    if "working_dir" not in options:
        options["working_dir"] = "/run"
    with open("DOCKER-COMMAND","w") as f:
        f.write("set -u -e -o pipefail\n")
        f.write(docker_command)   
    full_docker_command = "bash DOCKER-COMMAND"
    stdout0 = docker_client.containers.run(
        docker_image, 
        full_docker_command, 
        **options
    )
    stdout = BytesIO(stdout0)
    try:        
        tar = tarfile.open(fileobj=stdout)
        result = {}
        for member in tar.getnames():
            data = tar.extractfile(member).read()
            rdata = read_data(data)
            result[member] = rdata
    except (ValueError, tarfile.CompressionError, tarfile.ReadError):
        result = read_data(stdout0)
finally:
    os.chdir(old_cwd)
    shutil.rmtree(tempdir, ignore_errors=True)
