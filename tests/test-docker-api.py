import docker as docker_module
import os, tempfile

cwd = os.getcwd()
tempdir = tempfile.mkdtemp(prefix="seamless-docker-transformer")
os.chdir(tempdir)

bash_header = """set -u -e -o pipefail
trap '' PIPE
trap 'jobs -p | xargs -r kill' EXIT
"""

with open("DOCKER-COMMAND", "w") as f:
    f.write(bash_header)
    f.write("bash COMMAND\n")

with open("COMMAND", "w") as f:
    f.write("python3 -c 'import numpy as np; np.save(\"test\",np.arange(12)*3)'; cat test.npy\n")

try:
    docker_client = docker_module.from_env()
    docker_image = "continuumio/anaconda3"
    options = {}
    if "volumes" not in options:
        options["volumes"] = {}
    volumes = options["volumes"]
    volumes[tempdir] = {"bind": "/run", "mode": "rw"}
    if "working_dir" not in options:
        options["working_dir"] = "/run"
    full_docker_command = "bash DOCKER-COMMAND"
    from docker.types import LogConfig
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
        from docker.errors import ContainerError
        stderr = container.logs(stdout=False, stderr=True)
        raise ContainerError(
            container, exit_status, full_docker_command, docker_image, stderr
        )

    stdout = None if stdout0 is None else b''.join(
        [line for line in stdout0]
    )
    os.chdir(cwd)
    with open("test-docker-api-RESULT.npy", "wb") as f:
        f.write(stdout)
    import numpy as np
    np.save("test-docker-api-ORIGINAL.npy",np.arange(12)*3)

finally:
    com = "rm -rf {}".format(os.path.abspath(tempdir))
    os.system(com)
