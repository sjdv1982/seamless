import os,shutil
import tempfile
import numpy as np
import tarfile
import json
import sys
from io import BytesIO
from silk import Silk
from silk.mixed.get_form import get_form
from requests.exceptions import ConnectionError
from urllib3.exceptions import ProtocolError
from seamless.core.transformation import SeamlessTransformationError

resultfile = "RESULT"

_creating_container = False
_to_exit = False
_sys_exit = False

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

def sighandler(signal, frame):
    global _creating_container, _to_exit, _sys_exit
    if _creating_container:
        _to_exit = True
        return
    if container is not None:
        try:
            container.stop(timeout=10)
        except:
            pass
        try:
            container.remove()
        except:
            pass
    try:
        os.chdir(old_cwd)
        shutil.rmtree(tempdir, ignore_errors=True)
    except:
        pass
    _sys_exit = True
    raise SystemExit() from None

old_cwd = os.getcwd()
try:
    import signal
    import docker as docker_module
    tempdir = tempfile.mkdtemp(prefix="seamless-docker-transformer")
    os.chdir(tempdir)
    container = None
    signal.signal(signal.SIGTERM, sighandler)
    options = docker_options.copy()
    if "environment" in options:
        env = options["environment"].copy()
    else:
        env = {}
    options["environment"] = env
    for pin in pins_:
        v = PINS[pin]
        if isinstance(v, Silk):
            v = v.unsilk
        storage, form = get_form(v)
        if storage.startswith("mixed"):
            raise TypeError("pin '%s' has '%s' data" % (pin, storage))
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
        bash_header = """set -u -e
""" # don't add "trap 'jobs -p | xargs -r kill' EXIT" as it gives serious problems

        f.write(bash_header)
        f.write(docker_command)
    full_docker_command = """bash -c '''
ls $(pwd) > /dev/null 2>&1 || (>&2 echo \"\"\"The Docker container cannot read the current directory.
Most likely, the container runs under a specific user ID,
which is neither root nor the user ID under which Seamless is running.
Docker image user ID: $(id -u)
Seamless user ID: {}\"\"\"; exit 126) && bash DOCKER-COMMAND'''""".format(os.getuid())
    try:
        try:
            _creating_container = True
            container = docker_client.containers.create(
                docker_image,
                full_docker_command,
                **options
            )
            if _to_exit:
                raise SystemExit() from None
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
        finally:
            _creating_container = False
        try:
            container.start()
            exit_status = container.wait()['StatusCode']

            stdout = container.logs(stdout=True, stderr=False)
            try:
                stdout = stdout.decode()
            except:
                pass
            stderr = container.logs(stdout=False, stderr=True)
            try:
                stderr = stderr.decode()
            except:
                pass

            if exit_status != 0:
                raise SeamlessTransformationError("""
Docker transformer exception
============================

Exit code: {}

*************************************************
* Command
*************************************************
{}
*************************************************
* Standard output
*************************************************
{}
*************************************************
* Standard error
*************************************************
{}
*************************************************
""".format(exit_status, docker_command, stdout, stderr)) from None
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

Error: Result file RESULT does not exist

*************************************************
* Command
*************************************************
{}
*************************************************
""".format(docker_command)
            try:
                stdout = container.logs(stdout=True, stderr=False)
                try:
                    stdout = stdout.decode()
                except Exception:
                    pass
                if len(stdout):
                    msg += """*************************************************
* Standard output
*************************************************
{}
*************************************************
""".format(stdout)
                stderr = container.logs(stdout=False, stderr=True)
                try:
                    stderr = stderr.decode()
                except Exception:
                    pass
                if len(stderr):
                    msg += """*************************************************
* Standard error
*************************************************
{}
*************************************************
""".format(stderr)
            except Exception:
                pass

            raise SeamlessTransformationError(msg)
        else:
            if len(stdout):
                print(stdout)
            if len(stderr):
                print(stderr, file=sys.stderr)
    finally:
        if not _sys_exit:
            try:
                container.remove()
            except:
                pass


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
    if not _sys_exit:
        if container is not None:
            try:
                container.stop(timeout=10)
            except:
                pass
            try:
                container.remove()
            except:
                pass
        try:
            os.chdir(old_cwd)
            shutil.rmtree(tempdir, ignore_errors=True)
        except:
            pass