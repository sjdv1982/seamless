import os, stat
import subprocess

DOCKER_SOCKET = "/var/run/docker.sock"
DOCKER_IMAGE = os.environ.get("DOCKER_IMAGE", "rpbs/seamless")

def check_docker_power():
    d = os.environ.get("SEAMLESS_DOCKER_DISABLED")
    if d is not None and d.strip() not in ("False", "FALSE", "0"):
        return False
    if not os.path.exists(DOCKER_SOCKET):
        return False    
    mode = os.stat(DOCKER_SOCKET).st_mode
    if stat.S_ISSOCK(mode):
        return os.access(DOCKER_SOCKET, os.R_OK | os.W_OK)  

def check_conda_power():
    return False  # Seamless has no support for creating conda environments on-the-fly

def check_ipython_power():
    return True

"""
validate_XXX return a tuple
- Element 0:
    - True: match
    - None: no match
    - False: invalid attribute
- Element 1: error message
"""

def validate_singularity():
    result = subprocess.run("which singularity", shell=True, capture_output=True)
    if result.returncode:
        return False
    return True

def validate_docker(environment):
    docker = environment.get("docker")
    if docker is None:
        return None, None
    err0 = "Malformed environment.docker attribute"
    if not isinstance(docker, dict):
        return False, err0
    if "name" not in docker:
        return False, err0
    if "version" in docker or "checksum" in docker:
        return None, "Not implemented: version or checksum"
    if docker["name"] == DOCKER_IMAGE:
        return True, None
    else:
        err = "Cannot execute code locally: current Docker image name is '{}', whereas '{}' is required"
        return None, err.format(DOCKER_IMAGE, docker["name"])


def validate_conda_environment(environment):
    from conda.models.match_spec import MatchSpec
    from conda.cli.python_api import Commands, run_command as conda_run
    condenv = environment.get("conda")
    if condenv is None:
        return None, None
    err0 = "Malformed environment.conda attribute"
    if not isinstance(condenv, dict):
        return False, err0
    err = ""
    try:
        for dep in condenv.get("dependencies", []):
            ms = MatchSpec(dep)
            info = conda_run(Commands.LIST, ["-f", ms.name])[0]
            for l in info.split("\n"):
                l = l.strip()
                if l.startswith("#"):
                    continue
                ll = l.split()
                if len(ll) < 2:
                    continue
                if ll[0] != ms.name:
                    continue
                if ms.version is None:
                    break
                if ms.version.match(ll[1]):                
                    break
                else:
                    msg = "Conda package '{}': {} installed, but {} required"
                    err += msg.format(ms.name, ll[1], ms.version) + "\n"
                    break
            else:
                err += "Conda package '{}' not installed\n".format(ms.name)
    except (KeyError, ValueError, AttributeError):
        return False, err0
    if len(err):
        return None, err.rstrip("\n")
    else:
        return True, None
        
    

power_checkers = {
    "ipython": check_ipython_power,
    "conda": check_conda_power,
    "docker": check_docker_power,
}

def validate_environment(environment):
    if not isinstance(environment, dict):
        raise TypeError("Malformed environment")
    for binary in environment.get("which", []):
        result = subprocess.run("which " +  binary, shell=True, capture_output=True)
        if result.returncode:
            raise ValueError("which: '{}' is not available in command line path'".format(binary))

    result_conda = validate_conda_environment(environment)
    result_docker = validate_docker(environment)
    powers = environment.get("powers", [])
    
    for power in powers:
        if power not in power_checkers:
            raise ValueError("Unknown environment power {}".format(power))
        has_power = power_checkers[power]()
        if not has_power:
            if power == "docker" and validate_singularity():
                continue
            raise ValueError("Environment power cannot be granted: '{}'".format(power))

    err = ""
    if result_docker[0] == False:
        err += "Docker:\n  " + str(result_docker[1]) + "\n"
    if result_conda[0] == False:
        err += "Conda:\n  " + str(result_conda[1]) + "\n"
    if len(err):
        raise ValueError("Environment error:\n" + err)

    err = ""
    if result_docker[0] in (None, True):
        if "docker" in powers:
            return
        if result_docker[0] == True:
            return
        if result_docker[1] is not None:
            err += "Docker:\n  " + str(result_docker[1]) + "\n"
    if result_conda[0] in (None, True):
        if "conda" in powers:
            return
        if result_conda[0] == True:
            return
        if result_conda[1] is not None:
            err += "Conda:\n  " + str(result_conda[1]) + "\n"
    if not len(err):
        if result_conda[0] is None and result_docker[0] is None:
            return
        err = "Unknown environment error"
    raise ValueError("Environment error:\n" + err)