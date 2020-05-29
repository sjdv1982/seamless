import os,shutil
import tempfile
import numpy as np
import tarfile
import json
import sys
from io import BytesIO
from seamless.silk import Silk
from seamless.mixed.get_form import get_form
from requests.exceptions import ConnectionError
from urllib3.exceptions import ProtocolError
from seamless.core.transformation import SeamlessTransformationError

resultfile = "RESULT"

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
    docker_client = docker_module.from_env()
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
    try:
        container = docker_client.containers.create(
            docker_image,
            full_docker_command,
            **options
        )
        try:
            container.start()
            exit_status = container.wait()['StatusCode']

            if exit_status != 0:
                stderr = container.logs(stdout=False, stderr=True).decode()
                raise SeamlessTransformationError("""
Docker transformer exception
============================

*************************************************
* Command
*************************************************
{}
*************************************************
Exit code: {}
*************************************************
* Standard error
*************************************************
{}
*************************************************
""".format(docker_command, exit_status, stderr)) from None
        except ConnectionError as exc:
            msg = "Unknown connection error"
            if len(exc.args) == 1:
                exc2 = exc.args[0]
                if isinstance(exc2, ProtocolError):
                    if len(exc2.args) == 2:
                        a, exc3 = exc2.args
                        msg = "Docker gave an error: {}: {}".format(a, exc3)
                        if a.startswith("Connection aborted"):
                            if isinstance(exc3, FileNotFoundError):
                                if len(exc3.args) == 2:
                                    a1, a2 = exc3.args
                                    if a1 == 2 or a2 == "No such file or directory":
                                        msg = "Cannot connect to Docker; did you expose the Docker socket to Seamless?"
            raise SeamlessTransformationError(msg) from None

        if not os.path.exists(resultfile):
            msg = """
Docker transformer exception
============================

*************************************************
* Command
*************************************************
{}
*************************************************
Error: Result file RESULT does not exist
""".format(docker_command)
            try:
                stderr = container.logs(stdout=False, stderr=True).decode()
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
    finally:
        container.remove()

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
