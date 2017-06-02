import subprocess
from subprocess import PIPE

try:
    import cson as cson_lib
    cson_lib.loads
    has_cson_lib = True
except Exception:
    has_cson_lib = False

has_cson_cmd = False
try:
    p = subprocess.Popen(["cson2json"], stdin=PIPE, stdout=PIPE, stderr=PIPE)
    json, err = p.communicate("{}".encode("utf-8"))
    if err:
        has_cson_cmd = False
    else:
        has_cson_cmd = True
except Exception:
    pass

if not has_cson_lib and not has_cson_cmd:
    msg = "You need either the cson Python package or the cson2json command line utility"
    raise ImportError(msg)

def _cson2json_cmd(cson):
    p = subprocess.Popen(["cson2json"], stdin=PIPE, stdout=PIPE, stderr=PIPE)
    json, err = p.communicate(cson.encode("utf-8"))
    if err:
        raise RuntimeError(err)
    return json.decode("utf-8")

def cson2json(cson):
    if has_cson_lib and not has_cson_cmd:
        return cson_lib.loads(cson)
    elif has_cson_cmd and not has_cson_lib:
        return _cson2json_cmd(cson)
    else:
        try:
            return cson_lib.loads(cson)
        except Exception:
            return _cson2json_cmd(cson)
