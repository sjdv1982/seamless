from ..mixed import MixedBase
from copy import deepcopy
import inspect, asyncio
from ..core.protocol.serialize import serialize_sync as serialize
from ..core.protocol.calculate_checksum import calculate_checksum_sync as calculate_checksum
from ..core.protocol.deep_structure import apply_hash_pattern_sync

def get_checksums(nodes):
    # TODO: deep cells
    checksums = set()
    for p, node in nodes.items():
        if node["type"] in ("link", "context"):
            continue
        untranslated = node.get("UNTRANSLATED")
        assert not untranslated, p
        checksum = node.get("checksum")
        if checksum is None:
            continue
        elif isinstance(checksum, str):
            checksums.add(checksum)
        else:
            for k,v in checksum.items():
                if v is not None:
                    checksums.add(v)
    return checksums

async def get_buffer_dict(manager, checksums):
    from ..core.protocol.get_buffer import get_buffer
    result = {}
    cachemanager = manager.cachemanager
    buffer_cache = cachemanager.buffer_cache
    coros = []
    checksums = list(checksums)
    async def get_buf(checksum):
        return await cachemanager.fingertip(checksum)
        return get_buffer(bytes.fromhex(checksum), buffer_cache)
    for checksum in checksums:    
        coro = get_buf(checksum)
        coros.append(coro)
    buffers = await asyncio.gather(*coros, return_exceptions=True)
    for checksum, buffer in zip(checksums, buffers):
        if not isinstance(buffer, Exception):
            result[checksum] = buffer
    return result

def get_buffer_dict_sync(manager, checksums):
    """This function can be executed if the asyncio event loop is already running"""

    from ..core.protocol.get_buffer import get_buffer
    if not asyncio.get_event_loop().is_running():
        coro = get_buffer_dict(
            manager, checksums
        )
        fut = asyncio.ensure_future(coro)
        asyncio.get_event_loop().run_until_complete(fut)
        return fut.result()
    
    result = {}
    buffer_cache = manager.cachemanager.buffer_cache    
    checksums = list(checksums)
    for checksum in checksums:
        buffer = get_buffer(bytes.fromhex(checksum), buffer_cache)
        result[checksum] = buffer
    return result

def add_zip(manager, zipfile):
    """
    Caches all checksum-to-buffer entries in zipfile
    All "file names" in the zipfile must be checksum hexes
    Note that caching without Redis only lasts 20 seconds 
    """
    buffer_cache = manager.cachemanager.buffer_cache
    for checksum in zipfile.namelist():
        checksum2 = bytes.fromhex(checksum)
        buffer = zipfile.read(checksum)
        buffer_cache.cache_buffer(checksum2, buffer)

def fill_checksum(manager, node, temp_path, composite=True):
    from ..core.utils import strip_source
    checksum = None
    subcelltype = None
    if node["type"] == "cell":
        celltype = node["celltype"]
    elif node["type"] == "transformer":
        if temp_path == "code":
            datatype = "code"
            if node["language"] == "python":
                celltype = "python"
                subcelltype = "transformer"
            else:
                celltype = "text"
        elif temp_path == "_main_module":
            celltype = "plain"
        else:
            celltype = "structured"
    elif node["type"] == "reactor":
        raise NotImplementedError ### livegraph branch, feature E2
    elif node["type"] == "macro":
        raise NotImplementedError ### livegraph branch, feature E3
    else:
        raise TypeError(node["type"])
    if celltype == "structured":
        if node["type"] in ("reactor", "transformer"):
            datatype = "mixed"
        else:
            datatype = node["datatype"]
    else:
        datatype = celltype
        if datatype == "code":
            if node["language"] == "python":
                datatype = "python"
            else:
                datatype = "text"
    temp_value = node.get("TEMP")
    if composite:
        if isinstance(temp_value, dict):
            temp_value = temp_value.get(temp_path)            
        elif temp_value is None:
            pass
        else:
            raise TypeError(temp_value)
    if temp_value is None:
        return
        
    if datatype == "python":
        if inspect.isfunction(temp_value):
            code = inspect.getsource(temp_value)
            code = strip_source(code)
            temp_value = code
    buf = serialize(temp_value, datatype, use_cache=False)
    checksum = calculate_checksum(buf)    

    if checksum is None:
        return
    if node.get("hash_pattern") is not None:
        hash_pattern = node["hash_pattern"]
        checksum = apply_hash_pattern_sync(
            checksum, hash_pattern
        )
    checksum = checksum.hex()
    if temp_path is None:
        temp_path = "value"
    if "checksum" not in node:
        node["checksum"] = {}
    temp_path = temp_path.lstrip("_")  
    node["checksum"][temp_path] = checksum
        
def fill_checksums(mgr, nodes, *, path=None):
    """Fills checksums in the nodes from TEMP, if untranslated 
    """
    from ..core.structured_cell import StructuredCell
    first_exc = None
    for p in nodes:
        node, old_checksum = None, None
        try:
            pp = path + p if path is not None else p
            node = nodes[p]
            if node["type"] in ("link", "context"):
                continue
            untranslated = node.get("UNTRANSLATED")
            if not untranslated:
                assert "TEMP" not in node, (node["path"], str(node["TEMP"])[:80])
                continue
            old_checksum = node.pop("checksum", None)
            if node["type"] == "transformer":
                fill_checksum(mgr, node, "input_auth")
                node2 = node.copy()
                node2.pop("hash_pattern", None)
                fill_checksum(mgr, node2, "code")
                if "checksum" in node2:
                    node["checksum"] = node2["checksum"]
                if node["with_result"]:
                    fill_checksum(mgr, node2, "result")
                if node["compiled"]:
                    fill_checksum(mgr, node2, "_main_module")
                if "checksum" in node2 and "checksum" not in node:
                    node["checksum"] = node2["checksum"]
            elif node["type"] == "reactor":
                fill_checksum(mgr, node, "io")
                fill_checksum(mgr, node, "code_start")
                fill_checksum(mgr, node, "code_update")
                fill_checksum(mgr, node, "code_stop")
            elif node["type"] == "cell":
                if node["celltype"] == "structured":
                    temp_path = "auth"
                else:
                    temp_path = "value"
                fill_checksum(mgr, node, temp_path, composite=False)
            else:
                raise TypeError(p, node["type"])
            node.pop("TEMP", None)
            if "checksum" not in node:
                if old_checksum is not None:
                    node["checksum"] = old_checksum
            else:
                if old_checksum is not None:
                    node["checksum"].update(old_checksum)
        except Exception as exc:
            if first_exc is None:
                first_exc = exc
            else:
                import traceback
                traceback.print_exc()
            if node is not None and old_checksum is not None:
                node["checksum"] = old_checksum
    if first_exc is not None:
        raise first_exc