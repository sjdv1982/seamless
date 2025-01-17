import os
import shutil
import tempfile
import tarfile
import json
import sys
import signal
from io import BytesIO
from urllib3.exceptions import ProtocolError

import numpy as np
from requests.exceptions import ConnectionError

from silk import Silk
from silk.mixed.get_form import get_form

from seamless.checksum.buffer_remote import _read_folders
from seamless.util import subprocess_ as subprocess
from seamless.util.environment import validate_singularity, check_docker_power
from seamless.workflow.core.transformation import SeamlessStreamTransformationError
from seamless.workflow.core.mount_directory import write_to_directory

resultfile = "RESULT"

_creating_container = False
_to_exit = False
_sys_exit = False


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


singularity_mode = False
if not check_docker_power():
    if validate_singularity():
        singularity_dir = os.environ.get("SEAMLESS_SINGULARITY_DIR")
        if singularity_dir is None:
            raise SeamlessStreamTransformationError(
                "No docker available, and SEAMLESS_SINGULARITY_DIR is not defined"
            )
        if not os.path.exists(singularity_dir):
            raise SeamlessStreamTransformationError(
                f"SEAMLESS_SINGULARITY_DIR '{singularity_dir}' does not exist"
            )
        singularity_file0 = os.path.join(singularity_dir, docker_image_)
        singularity_file = None
        for ext in "sif", "simg":
            singularity_file00 = singularity_file0 + "." + ext
            if os.path.exists(singularity_file00):
                singularity_file = singularity_file00
                break
        if singularity_file is None:
            raise SeamlessStreamTransformationError(
                f"SEAMLESS_SINGULARITY_DIR '{singularity_dir}' does not contain {docker_image_}.sif or .simg"
            )
        singularity_mode = True
    else:
        raise SeamlessStreamTransformationError(
            "Docker and singularity are not available"
        )

if singularity_mode:
    # adapted from bash transformer
    try:
        process = None
        tempdir = tempfile.mkdtemp(prefix="seamless-singularity-transformer")
        os.chdir(tempdir)
        signal.signal(signal.SIGTERM, sighandler)
        env = {}
        for pin in pins_:
            if pin == "pins_":
                continue
            if pin in ["docker_command", "docker_image_", "docker_options"]:
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
                    write_to_directory(
                        pin, v, cleanup=False, deep=False, text_only=False
                    )
                    env[pin] = pin
                    continue
            storage, form = get_form(v)
            if storage.startswith("mixed"):
                raise TypeError("pin '%s' has '%s' data" % (pin, storage))
            if storage == "pure-plain":
                if isinstance(form, str):
                    vv = str(v)
                    if not vv.endswith("\n"):
                        vv += "\n"
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
                        np.save(pinf, v, allow_pickle=False)
        bash_header = f"""set -u -e
trap 'jobs -p | xargs -r kill' EXIT
declare -p {" ".join(env.keys())} > __env__
"""
        with open("__env__", "w") as f:
            for k, v in env.items():
                f.write(f"{k}=''")
        with open("__BASHCODE__", "w") as f:
            f.write(docker_command)
        singularity_command = f"""singularity exec \
--containall --no-init --no-umask --no-eval \
--env-file __env__ \
--bind $(pwd):/run \
{singularity_file} \
bash -c 'cd /run; bash ./__BASHCODE__'
"""
        full_singularity_command = bash_header + singularity_command
        process = subprocess.Popen(
            full_singularity_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            executable="/bin/bash",
            env=env,
        )
        for line in process.stdout:
            try:
                line = line.decode()
            except UnicodeDecodeError:
                pass
            print(line, end="")
        process.wait()

        if process.returncode:
            raise SeamlessStreamTransformationError(
                """
Singularity transformer exception
==========================

Error: Return code {}

*************************************************
* Command
*************************************************
{}
*************************************************
""".format(
                    process.returncode, singularity_command
                )
            ) from None
        if not os.path.exists(resultfile):
            msg = """
Singularity transformer exception
=================================

Error: Result file/folder RESULT does not exist

*************************************************
* Command
*************************************************
{}
*************************************************
""".format(
                singularity_command
            )
            raise SeamlessStreamTransformationError(msg)

        if os.path.isdir(resultfile):
            result0 = {}
            for dirpath, _, filenames in os.walk(resultfile):
                for filename in filenames:
                    full_filename = os.path.join(dirpath, filename)
                    assert full_filename.startswith(resultfile + "/")
                    member = full_filename[len(resultfile) + 1 :]
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

    # /adapted from bash transformer
else:  # "docker" mode
    _dind_mounts = []
    try:
        import signal
        import docker as docker_module

        tempdir = tempfile.mkdtemp(prefix="seamless-docker-transformer")
        os.chdir(tempdir)
        container = None
        signal.signal(signal.SIGTERM, sighandler)
        options = {}
        env = {}
        options["environment"] = env
        for pin in pins_:
            if pin == "pins_":
                continue
            if pin in ["docker_command", "docker_image_", "docker_options"]:
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
                    if os.environ.get(
                        "DOCKER_IMAGE"
                    ):  # we are running inside a Docker container
                        _dind_mounts.append((v, pin))
                    os.symlink(v, pin)
                    continue
                elif FILESYSTEM[pin]["mode"] == "directory":
                    write_to_directory(
                        pin, v, cleanup=False, deep=False, text_only=False
                    )
                    env[pin] = pin
                    continue
            storage, form = get_form(v)
            if storage.startswith("mixed"):
                raise TypeError("pin '%s' has '%s' data" % (pin, storage))
            if storage == "pure-plain":
                if isinstance(form, str):
                    vv = str(v)
                    if not vv.endswith("\n"):
                        vv += "\n"
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
                        np.save(pinf, v, allow_pickle=False)
        if _dind_mounts:
            warn0 = "\n    ".join([f"{pin} -> {v}" for v, pin in _dind_mounts])
            warn = f"""WARNING: Docker transformer launched from within a Docker container.
The Docker containers will run side by side under the host, symbolic links will not normally work.

The following pins access their buffer through symbolic links:

    {warn0}

"""
            print(warn, file=sys.stderr)
        docker_client = docker_module.from_env()
        volumes = {}
        options["volumes"] = volumes
        volumes[tempdir] = {"bind": "/run", "mode": "rw"}
        if _read_folders:
            for folder in _read_folders:
                volumes[folder] = {"bind": folder, "mode": "ro"}

        if "working_dir" not in options:
            options["working_dir"] = "/run"
        with open("DOCKER-COMMAND", "w") as f:
            bash_header = """set -u -e
trap 'chmod -R 777 /run' EXIT
"""  # don't add "trap 'jobs -p | xargs -r kill' EXIT" as it gives serious problems

            f.write(bash_header)
            f.write(docker_command)
            f.write("\nchmod -R 777 /run")
        options.update(docker_options)
        full_docker_command = """bash -c '''
ls $(pwd) > /dev/null 2>&1 || (>&2 echo \"\"\"The Docker container cannot read the mounted temporary directory.
Most likely, the container runs under a specific user ID,
which is neither root nor the user ID under which Seamless is running.
Docker image user ID: $(id -u)
Seamless user ID: {}\"\"\"; exit 126) && bash DOCKER-COMMAND'''""".format(
            os.getuid()
        )
        try:
            try:
                _creating_container = True
                container = docker_client.containers.create(
                    docker_image_, full_docker_command, **options
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
                raise SeamlessStreamTransformationError(msg) from None
            finally:
                _creating_container = False
            try:
                container.start()
                logs = container.logs(stdout=True, stderr=True, stream=True)
                for bufline in logs:
                    try:
                        line = bufline.decode()
                        print(line, end="")
                    except UnicodeDecodeError:
                        sys.stdout.buffer.write(bufline)
                exit_status = container.wait()["StatusCode"]

                if exit_status != 0:
                    raise SeamlessStreamTransformationError(
                        """
Docker transformer exception
============================

Exit code: {}

*************************************************
* Command
*************************************************
{}
*************************************************
""".format(
                            exit_status, docker_command
                        )
                    ) from None
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
                raise SeamlessStreamTransformationError(msg) from None

            if not os.path.exists(resultfile):
                msg = """
Docker transformer exception
============================

Error: Result file/folder RESULT does not exist

*************************************************
* Command
*************************************************
{}
*************************************************
""".format(
                    docker_command
                )
                raise SeamlessStreamTransformationError(msg)
        finally:
            if not _sys_exit:
                try:
                    container.remove()
                except:
                    pass

        if os.path.isdir(resultfile):
            result0 = {}
            for dirpath, _, filenames in os.walk(resultfile):
                for filename in filenames:
                    full_filename = os.path.join(dirpath, filename)
                    assert full_filename.startswith(resultfile + "/")
                    member = full_filename[len(resultfile) + 1 :]
                    data = open(full_filename, "rb").read()
                    rdata = read_data(data)
                    result0[member] = rdata
            result = {}
            for k in sorted(result0.keys()):
                result[k] = result0[k]
                del result0[k]
        else:
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
