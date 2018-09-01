from weakref import WeakValueDictionary, WeakSet
from .cell import Cell, PythonCell, PyMacroCell, celltypes, cell as make_cell
from .context import Context
from contextlib import contextmanager
from copy import deepcopy

celltypes_rev = {v:k for k,v in celltypes.items()}

_lib = {}
_cells = {}
_boundcells = WeakSet()

def _update_old_keys(oldkeys, oldlib, lib, name, on_macros):
    for key in oldkeys:
        if key not in _cells:
            continue
        oldcells = _cells[key]
        fullkey = name + "." + key
        for oldcell in oldcells:
            is_macro = isinstance(oldcell, (PythonCell, PyMacroCell))
            if is_macro != on_macros:
                continue
            manager = oldcell._get_manager()
            exists = False
            if key in lib:
                celltype, cell_content, checksum, text_checksum = lib[key]
                old_celltype, old_cell_content, old_checksum, old_text_checksum = oldlib[key]
                if old_celltype == celltype:
                    exists = True
            if exists:
                if old_checksum != checksum or old_text_checksum != text_checksum:
                    if celltype in ("python", "macro", "transformer", "reactor"):
                        cell_content, _, _ = cell_content
                    manager.set_cell(oldcell, cell_content, from_pin=True)
            else:
                if oldcell not in _boundcells:
                    print("Warning: Library key %s deleted, %s set to None" % (key, oldcell))
                manager.set_cell(oldcell, None, from_pin=True)


def register(name, lib):
    assert isinstance(name, str)
    assert isinstance(lib, dict)
    if name not in _lib:
        _lib[name] = lib
        return
    oldlib = _lib[name]
    oldkeys = list(oldlib.keys())
    _update_old_keys(oldkeys, oldlib, lib, name, on_macros=True)
    _update_old_keys(oldkeys, oldlib, lib, name, on_macros=False)
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
    for childname, child in ctx._children.items():
        if prepath is None:
            path = childname
        else:
            path = prepath + "." + childname
        if isinstance(child, Context):
            _build(child, result, path)
        elif isinstance(child, Cell):
            celltype = celltypes_rev[type(child)]
            if celltype == "signal":
                continue
            if celltype in ("python", "macro", "transformer", "reactor"):
                val = deepcopy(child._val)
                cell_content = (val, child.is_function, child.func_name)
            else:
                cell_content = deepcopy(child._val)
            child.checksum()
            checksum = child._last_checksum
            text_checksum = None
            if child._has_text_checksum:
                text_checksum = child._last_text_checksum
            result[path] = celltype, cell_content, checksum, text_checksum

def build(ctx):
    result = {}
    _build(ctx, result, None)
    return result

def libcell(path):
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
    assert key in lib, key #library key must be in library
    celltype, cell_content, checksum, text_checksum = lib[key]
    c = make_cell(celltype)
    if celltype in ("python", "macro", "transformer", "reactor"):
        val, is_function, func_name = cell_content
        c._val = deepcopy(val)
        c.is_function = is_function
        c.func_name = func_name
    else:
        c._val = deepcopy(cell_content)
    c._last_checksum = checksum
    if c._has_text_checksum:
        c._last_text_checksum = text_checksum
    c._status = c.StatusFlags.OK
    c._authoritative = False
    if key not in _cells:
        _cells[key] = WeakSet()
    _cells[key].add(c)
    if boundcell:
        _boundcells.add(c)
    return c
