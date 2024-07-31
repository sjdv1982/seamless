"""Converts bash transformation dicts to standard (Python)."""

from copy import deepcopy


_bash_checksums:dict | None = None
def get_bash_checksums():
    from .stdgraph import load as load_stdgraph
    from seamless.workflow.core.direct.run import _get_semantic
    global _bash_checksums
    if _bash_checksums is None:        
        sctx = load_stdgraph("bash_transformer")
        executor_code_checksum = sctx.executor_code.checksum
        executor_code_buffer = sctx.executor_code.buffer
        executor_code = sctx.executor_code.value
        semantic_code_checksum = _get_semantic(
            executor_code, bytes.fromhex(executor_code_checksum)
        )
        _bash_checksums = {}
        _bash_checksums["executor_code_checksum"] = executor_code_checksum
        _bash_checksums["executor_code_buffer"] = executor_code_buffer
        _bash_checksums["semantic_code_checksum"] = semantic_code_checksum

        sctx = load_stdgraph("bashdocker_transformer")
        executor_code_checksum = sctx.executor_code.checksum
        executor_code_buffer = sctx.executor_code.buffer
        executor_code = sctx.executor_code.value
        '''
        ### for debugging
        import os, seamless
        executor_code = open(os.path.join(os.path.dirname(__file__), "../graphs/bashdocker_transformer/executor.py")).read()
        executor_code_buffer = executor_code.encode()
        executor_code_checksum = seamless.calculate_checksum(executor_code_buffer, hex=True)
        ###
        '''            
        semantic_code_checksum = _get_semantic(
            executor_code, bytes.fromhex(executor_code_checksum)
        )
        _bash_checksums["docker_executor_code_checksum"] = executor_code_checksum
        _bash_checksums["docker_executor_code_buffer"] = executor_code_buffer
        _bash_checksums["docker_semantic_code_checksum"] = semantic_code_checksum

    return _bash_checksums.copy()

def unbashify_docker(transformation_dict, semantic_cache, env: dict, execution_metadata:dict):
    from seamless.workflow.core.direct.run import prepare_code, prepare_transformation_pin_value
    tdict = deepcopy(transformation_dict)
    tdict["__language__"] = "python"
    tdict["__output__"] = ("result",) + tuple(transformation_dict["__output__"][1:])
    bash_checksums = get_bash_checksums()
    
    pins = [p for p in sorted(tdict.keys()) if p != "code" and not p.startswith("__")]
    
    docker = env.pop("docker")
    docker_image = docker["name"]
    docker_options = docker.get("options", {})
    # TODO: pass on version and checksum as well?
    if "powers" not in env:
        env["powers"] = []
    env["powers"].append("docker")
    env2_checksum = prepare_transformation_pin_value(env, "plain").hex()
    tdict["__env__"] = env2_checksum

    new_pins = {
        "pins_": (pins, "plain"),
        "docker_image_": (docker_image, "str"),
        "docker_options": (docker_options, "plain"),
    }
    for pinname, (value, celltype) in new_pins.items():
        p_checksum = prepare_transformation_pin_value(value, celltype).hex()
        tdict[pinname] = (celltype, None, p_checksum)

    code_pin = tdict["code"]
    tdict["docker_command"] = code_pin
    semantic_code_checksum = prepare_code(
        bash_checksums["docker_semantic_code_checksum"], 
        bash_checksums["docker_executor_code_buffer"],
        bash_checksums["docker_executor_code_checksum"]
    )                                                         
    tdict["code"] = ("python", "transformer", semantic_code_checksum.hex())
    semkey = (semantic_code_checksum.bytes(), "python", "transformer")
    semantic_cache[semkey] = [bytes.fromhex(bash_checksums["docker_executor_code_checksum"])]

    execution_metadata["Language bridge"] = {
        "Source language": "bash",
        "Executor language": "python",
        "Executor": "Seamless standard graph: bashdocker_transformer",
        "Executor checksum": bash_checksums["docker_executor_code_checksum"],
    }

    return tdict

def unbashify(transformation_dict:dict, semantic_cache, execution_metadata:dict):
    from seamless.workflow.core.direct.run import prepare_code, prepare_transformation_pin_value
    from seamless.workflow.core.manager import Manager
    from ..core.environment import (
        validate_conda_environment,
        validate_docker
    )

    assert transformation_dict["__language__"] == "bash"
    assert "bashcode" not in transformation_dict
    assert "pins_" not in transformation_dict

    env_checksum = transformation_dict.get("__env__")
    env = None
    if env_checksum is not None:
        manager = Manager()
        env = manager.resolve(bytes.fromhex(env_checksum), celltype="plain", copy=True)

    if env is not None and env.get("docker") is not None:
        ok1 = validate_conda_environment(env)[0]
        ok2 = validate_docker(env)[0]
        if not (ok1 or ok2):
            return unbashify_docker(transformation_dict, semantic_cache, env, execution_metadata)

    tdict = deepcopy(transformation_dict)
    tdict["__language__"] = "python"
    tdict["__output__"] = ("result",) + tuple(transformation_dict["__output__"][1:])
    bash_checksums = get_bash_checksums()
    
    pins = [p for p in sorted(tdict.keys()) if p != "code" and not p.startswith("__")]
    pins_checksum = prepare_transformation_pin_value(pins, "plain").hex()
    tdict["pins_"] = ("plain", None, pins_checksum)
    conda_environment_ = env.get("conda_bash_env_name") if env is not None else ""
    conda_environment_checksum = prepare_transformation_pin_value(conda_environment_, "str").hex()
    tdict["conda_environment_"] = ("str", None, conda_environment_checksum)
    code_pin = tdict["code"]
    tdict["bashcode"] = code_pin
    semantic_code_checksum = prepare_code(
        bash_checksums["semantic_code_checksum"], 
        bash_checksums["executor_code_buffer"],
        bash_checksums["executor_code_checksum"]
    )                                                         
    tdict["code"] = ("python", "transformer", semantic_code_checksum.hex())
    semkey = (semantic_code_checksum.bytes(), "python", "transformer")
    semantic_cache[semkey] = [bytes.fromhex(bash_checksums["executor_code_checksum"])]

    execution_metadata["Language bridge"] = {
        "Source language": "bash",
        "Executor language": "python",
        "Executor": "Seamless standard graph: bash_transformer",
        "Executor checksum": bash_checksums["executor_code_checksum"],
    }

    return tdict