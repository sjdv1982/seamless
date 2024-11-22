def tf_get_buffer(transformation):
    from seamless import Checksum
    from seamless.checksum.json import json_dumps

    assert isinstance(transformation, dict)
    d = {}
    for k in transformation:
        if k in (
            "__compilers__",
            "__languages__",
            "__meta__",
            "__env__",
            "__code_checksum__",
        ):
            continue
        v = transformation[k]
        if k in ("__language__", "__output__", "__as__", "__format__"):
            d[k] = v
            continue
        if k.startswith("SPECIAL__"):
            continue
        celltype, subcelltype, checksum = v
        if isinstance(checksum, Checksum):
            checksum = checksum.value
        d[k] = celltype, subcelltype, checksum
    buffer = json_dumps(d, as_bytes=True) + b"\n"
    return buffer


def extract_dunder(transformation_dict):
    tf_dunder = {}
    for k in ("__compilers__", "__languages__", "__meta__", "__env__"):
        if k in transformation_dict:
            tf_dunder[k] = transformation_dict[k]
    if not len(tf_dunder):
        return None

    return tf_dunder
