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
    from docker.errors import ContainerError
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
                vv = str(v) + "\n"
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
        stdout0 = container.attach(stdout=True, stderr=False, stream=True)
        container.start()
        exit_status = container.wait()['StatusCode']
        container.remove()

        if exit_status != 0:
            stderr = container.logs(stdout=False, stderr=True)
            raise ContainerError(
                container, exit_status, full_docker_command, docker_image, stderr
            )

        stdout = None if stdout0 is None else b''.join(
            [line for line in stdout0]
        )
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
    stdout_io = BytesIO(stdout)
    try:
        tar = tarfile.open(fileobj=stdout_io)
        result = {}
        for member in tar.getnames():
            data = tar.extractfile(member).read()
            rdata = read_data(data)
            result[member] = rdata
    except (ValueError, tarfile.CompressionError, tarfile.ReadError):
        result = read_data(stdout)
finally:
    os.chdir(old_cwd)
    shutil.rmtree(tempdir, ignore_errors=True)
