"""Converts bash transformation dicts to standard (Python)."""

from copy import deepcopy


_bash_checksums:dict | None = None
def get_bash_checksums():
    from .stdgraph import load as load_stdgraph
    from seamless.core.direct.run import _get_semantic
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

    return _bash_checksums.copy()

def unbashify(transformation_dict, semantic_cache):
    from seamless.core.direct.run import prepare_code, prepare_transformation_pin_value
    assert transformation_dict["__language__"] == "bash"
    assert "bashcode" not in transformation_dict
    assert "pins_" not in transformation_dict

    tdict = deepcopy(transformation_dict)
    tdict["__language__"] = "python"
    # TODO: will this work directly with different return types / hash patterns?
    tdict["__output__"] = ("result", "bytes", None)
    bash_checksums = get_bash_checksums()
    
    pins = [p for p in sorted(tdict.keys()) if p != "code" and not p.startswith("__")]
    pins_checksum = prepare_transformation_pin_value(pins, "plain").hex()
    tdict["pins_"] = ("plain", None, pins_checksum)
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
    return tdict