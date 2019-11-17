from ..mixed import MixedBase
from copy import deepcopy
from ..core.protocol.serialize import serialize_sync as serialize
from ..core.protocol.calculate_checksum import calculate_checksum_sync as calculate_checksum

def copy_context(nodes, connections, path):
    new_nodes = {}
    new_connections = []
    for p in nodes:
        if p[:len(path)] != path:
            continue
        pp = p[len(path):]
        node = deepcopy(nodes[p])
        node["path"] = pp
        new_nodes[pp] = node
    for con in connections:
        source, target = con["source"], con["target"]
        if source[:len(path)] != path:
            continue
        if target[:len(path)] != path:
            continue
        new_con = deepcopy(con)
        new_con["source"] = source[len(path):]
        new_con["target"] = target[len(path):]
        new_connections.append(new_con)


def fill_checksum(manager, node, temp_path):
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
        else:
            celltype = "structured"
    else:
        raise NotImplementedError ### cache branch
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
    if temp_path != "temp":
        if isinstance(temp_value, dict):
            temp_value = temp_value.get(temp_path)
        elif temp_value is None:
            pass
        else:
            raise TypeError(temp_value)
    if temp_value is None:
        return
        
    buf = serialize(temp_value, datatype, use_cache=False)
    checksum = calculate_checksum(buf)

    if checksum is None:
        return
    checksum = checksum.hex()
    if temp_path is None:
        temp_path = "value"
    if "checksum" not in node:
        node["checksum"] = {}
    node["checksum"][temp_path] = checksum       
        
def fill_checksums(mgr, nodes, *, path=None):
    """Fills checksums in the nodes from TEMP, if untranslated 
    """
    from ..core.structured_cell import StructuredCell    
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
                fill_checksum(mgr, node, "code")
                if node["with_result"]:
                    fill_checksum(mgr, node, "result")
                if node["compiled"]:
                    fill_checksum(mgr, node, "main_module")
            elif node["type"] == "reactor":
                fill_checksum(mgr, node, "io")
                fill_checksum(mgr, node, "code_start")
                fill_checksum(mgr, node, "code_update")
                fill_checksum(mgr, node, "code_stop")
            elif node["type"] == "cell":
                fill_checksum(mgr, node, "temp")
            else:
                raise TypeError(p, node["type"])
            node.pop("TEMP", None)
            if "checksum" not in node and old_checksum is not None:
                node["checksum"] = old_checksum
        except Exception:
            import traceback
            traceback.print_exc()
            if node is not None and old_checksum is not None:
                node["checksum"] = old_checksum