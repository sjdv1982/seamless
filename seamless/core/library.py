from weakref import WeakValueDictionary, WeakSet
from .cell import Cell, PythonCell, PyMacroCell, celltypes, cell as make_cell, mixedcell
from .context import Context
from contextlib import contextmanager
from copy import deepcopy

_lib = {}
_cells = {}
_boundcells = WeakSet()

celltypes_rev = {v:k for k,v in celltypes.items()}

def _update_old_keys(oldkeys, oldlib, lib, on_macros):
    for key in oldkeys:
        if key not in _cells:
            continue
        oldcells = _cells[key]
        for oldcell in oldcells:
            is_macro = isinstance(oldcell, (PythonCell, PyMacroCell))
            if is_macro != on_macros:
                continue
            if oldcell._destroyed:
                continue
            exists = False
            if key in lib:
                celltype, checksum = lib[key]
                old_celltype, old_checksum = oldlib[key]
                if old_celltype == celltype:
                    exists = True
            if exists:
                if old_checksum != checksum:
                    ###value_cache.decref(old_checksum, has_auth=True) #TODO: malfunctioning...
                    oldcell._get_manager().set_cell_checksum(oldcell, checksum)
            else:
                if oldcell not in _boundcells:
                    print("Warning: Library key %s deleted, %s set to None" % (key, oldcell))
                oldcell.set(None)

def register(name, lib):
    assert isinstance(name, str)
    assert isinstance(lib, dict)
    if name not in _lib:
        _lib[name] = lib
        return
    oldlib = _lib[name]
    oldkeys = list(oldlib.keys())
    _update_old_keys(oldkeys, oldlib, lib, on_macros=True)
    _update_old_keys(oldkeys, oldlib, lib, on_macros=False)
    _lib[name] = lib

_bound = None
@contextmanager
def bind(name):
    if name is None:
        yield
        return
    global _bound
    oldbound = _bound
    _bound = name
    yield
    _bound = oldbound

def _build(ctx, result, prepath):
    manager = ctx._get_manager()
    mgr_cell_cache = manager.cell_cache
    mgr_value_cache = manager.value_cache
    for childname, child in ctx._children.items():
        if prepath is None:
            path = childname
        else:
            path = prepath + "." + childname
        if isinstance(child, Context):
            _build(child, result, path)
        elif isinstance(child, Cell):
            celltype = celltypes_rev[type(child)]
            checksum = mgr_cell_cache.cell_to_buffer_checksums.get(child)            
            buffer = mgr_value_cache.get_buffer(checksum)
            if buffer is not None:
                _, _, buffer = buffer
            value_cache.incref(checksum, buffer, has_auth=True)            
            result[path] = celltype, checksum


def build(ctx):
    from .context import Context
    assert isinstance(ctx, Context), type(ctx)
    result = {}
    _build(ctx, result, None)
    return result

def _libcell(path, mandated_celltype, *args, **kwargs):
    if path.startswith("."):
        assert _bound is not None #a library context name must be bound
        libname, key = _bound , path[1:]
        boundcell = True
    else:
        pos = path.find(".")
        assert pos > -1 #must be at least one dot in the path
        libname, key = path[:pos], path[pos+1:]
        boundcell = False
    assert libname in _lib, libname #library name must have been registered
    lib = _lib[libname]
    assert key in lib, (key, list(lib.keys())) #library key must be in library
    celltype, checksum = lib[key]
    assert mandated_celltype is None or mandated_celltype == celltype, (mandated_celltype, celltype)
    c = make_cell(celltype, *args, **kwargs)
    c._prelim_checksum = checksum
    if key not in _cells:
        _cells[key] = WeakSet()
    _cells[key].add(c)
    if boundcell:
        _boundcells.add(c)
    c._lib_path = path
    return c

def lib_has_path(libname, path):
    assert libname in _lib
    #print("lib_has_path", libname, path, path in _lib[libname], _lib[libname])
    return path in _lib[libname]

def libcell(path, celltype=None):
    return _libcell(path, celltype)

def lib_get_value(checksum, cell):
    raise NotImplementedError # livegraph branch
    celltype = celltypes_rev[type(cell)]
    buffer = value_cache.get_buffer(checksum)[2]
    assert buffer is not None
    result = deserialize(
        celltype, None, "lib_get_value",
        buffer, from_buffer = True, buffer_checksum = None,
        source_access_mode = None,
        source_content_type = None,
    )    
    obj = result[2]
    if celltype == "mixed":
        obj = obj[2]
    return obj



from .cache.value_cache import ValueCache
value_cache = ValueCache(None)
from .protocol.deserialize import deserialize