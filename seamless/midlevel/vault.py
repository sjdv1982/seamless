import os

SMALL_BIG_THRESHOLD = 100000  # for now, the same as buffer_cache.SMALL_BUFFER_LIMIT

def save_vault(dirname, annotated_checksums, buffer_dict):
    dirs = {}
    for dep in ("independent", "dependent"):
        for size in ("small", "big"):
            dirn = os.path.join(dirname, dep, size)
            os.makedirs(dirn, exist_ok=True)
            with open(os.path.join(dirn, ".gitkeep"), "w") as f:
                pass
            dirs[dep, size] = dirn

    for checksum, is_dependent in annotated_checksums:
        buffer = buffer_dict[checksum]
        size = "small" if len(buffer) <= SMALL_BIG_THRESHOLD else "big"
        dep = "dependent" if is_dependent else "independent"
        dirn = dirs[dep, size]
        filename = os.path.join(dirn, checksum)
        with open(filename, "wb") as f:
            f.write(buffer)

def load_vault_flat(dirname, incref):
    from ..calculate_checksum import calculate_checksum
    from ..core.cache.buffer_cache import empty_dict_checksum, empty_list_checksum
    result = []
    for _, _, files in os.walk(dirname):
        for filename in files:
            if filename.startswith("."):
                continue
            checksum = filename
            if checksum in (empty_dict_checksum, empty_list_checksum):
                continue
            checksum2 = bytes.fromhex(checksum)
            filename2 = os.path.join(dirname, filename)
            with open(filename2, "rb") as f:
                buffer = f.read()
            checksum3 = calculate_checksum(buffer)
            if checksum3 != checksum2:
                raise ValueError("Incorrect checksum for vault file '{}'".format(filename2))
            buffer_cache.cache_buffer(checksum2, buffer)
            if incref:
                buffer_cache.incref(checksum2, authoritative=False)
            result.append(checksum)
    return result

def load_vault(dirname, incref=False):
    if not os.path.exists(dirname):
        raise ValueError(dirname)
    result = []
    ok = False
    for dep in ("independent", "dependent"):
        for size in ("small", "big"):
            dirn = os.path.join(dirname, dep, size)
            if not os.path.exists(dirn):
                continue
            ok = True
            result += load_vault_flat(dirn, incref)
    if not ok:
        raise ValueError("{} does not seem to be a Seamless vault".format(dirname))
    return result

from ..core.cache.buffer_cache import buffer_cache