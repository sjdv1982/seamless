from ..mixed import MixedBase
from copy import deepcopy
from ..core.link import Link as core_link
from ..core.protocol import deserialize
from ..core import context as core_context, cell as core_cell
from ..core.macro_mode import macro_mode_off

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
    silk, buffered = False, False
    if celltype == "structured":
        buffered = node["buffered"]
        if node["type"] in ("reactor", "transformer"):
            silk = not node["plain"]
            datatype = "mixed" if not node["plain"] else "plain"
        else:
            silk = node["silk"]
            datatype = node["datatype"]
    else:
        datatype = celltype
        if datatype == "code":
            if node["language"] == "python":
                datatype = "python"
            else:
                datatype = "text"
    temp_value = node.get("TEMP")
    if temp_path:
        if isinstance(temp_value, dict):
            temp_value = temp_value.get(temp_path)
        elif temp_value is None:
            pass
        else:
            raise TypeError(temp_value)
    if temp_value is None:
        return
    
    with macro_mode_off():
        ctx = core_context(toplevel=True)
        ctx._manager = manager
        ctx.cell = core_cell(datatype)
        ctx.cell.set(temp_value)
        checksum = ctx.cell.checksum 
    ctx.destroy()  

    if checksum is None:
        return
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
                fill_checksum(mgr, node, "input")
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
                fill_checksum(mgr, node, None)
            else:
                raise TypeError(p, node["type"])
            node.pop("TEMP", None)
            if "checksum" not in node and old_checksum is not None:
                node["checksum"] = old_checksum
        except:
            import traceback
            traceback.print_exc()
            if node is not None and old_checksum is not None:
                node["checksum"] = old_checksum