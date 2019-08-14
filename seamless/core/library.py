from weakref import WeakValueDictionary, WeakSet
from contextlib import contextmanager
from copy import deepcopy

from .cell import Cell, PythonCell, PyMacroCell, celltypes, cell as make_cell

class Library(dict):
    pass

_lib = {}
_root_to_libname = {}
_cells = {}
_boundcells = WeakSet()

celltypes_rev = {v:k for k,v in celltypes.items()}

def _update_old_keys(oldkeys, oldlib, lib, old_root, root):
    from .manager.tasks.macro_update import MacroUpdateTask
    cachemanager = root._get_manager().cachemanager
    old_cachemanager = old_root._get_manager().cachemanager
    for key in oldkeys:
        if key not in _cells:
            continue
        oldcells = _cells[key]
        for oldcell, macro in oldcells:
            if oldcell._destroyed:
                continue
            exists = False
            if key in lib:
                celltype, checksum, _ = lib[key]
                old_celltype, old_checksum, _ = oldlib[key]
                if old_celltype == celltype:
                    exists = True
            if exists:
                if old_checksum != checksum:
                    oldcell.set_checksum(checksum.hex())
                if macro is not None:
                    manager = macro._get_manager()
                    manager.cancel_macro(macro, False)
                    MacroUpdateTask(manager, macro).launch()
            else:
                if oldcell not in _boundcells:
                    print("Warning: Library key '%s' deleted, %s set to None" % (key, oldcell))
                oldcell.set_checksum(None)

def register(name, lib, root):
    assert isinstance(name, str)
    assert isinstance(lib, dict)
    if name not in _lib:
        _lib[name] = lib, root
        if root not in _root_to_libname:
            _root_to_libname[root] = []
        _root_to_libname[root].append(name)
        return
    oldlib, old_root = _lib[name]
    oldkeys = list(oldlib.keys())
    _update_old_keys(
        oldkeys, oldlib, lib, 
        old_root, root
    )
    unregister(name)
    if root not in _root_to_libname:
        _root_to_libname[root] = []
    _root_to_libname[root].append(name)    
    _lib[name] = lib, root

def unregister(name):
    lib, root = _lib[name]
    cachemanager = root._get_manager().cachemanager
    for entry in lib.values():
        _, checksum, _ = entry
        if checksum is None:
            continue
        cachemanager.decref_checksum(checksum, lib, True)
    _root_to_libname[root].remove(name)

def unregister_all(root):
    if root not in _root_to_libname:
        return
    for libname in list(_root_to_libname[root]):
        unregister(libname)
    _root_to_libname.pop(root)

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
    cachemanager = manager.cachemanager
    livegraph = manager.livegraph
    for childname, child in ctx._children.items():
        if prepath is None:
            path = childname
        else:
            path = prepath + "." + childname
        if isinstance(child, Context):
            _build(child, result, path)
        elif isinstance(child, Cell):
            is_buffercell = child in livegraph.buffercells
            celltype, checksum = child._celltype, child._checksum
            #print("INCREF", checksum.hex())
            cachemanager.incref_checksum(checksum, result, True)            
            result[path] = celltype, checksum, is_buffercell


def build(ctx):
    from .context import Context
    assert isinstance(ctx, Context), type(ctx)
    result = Library()
    root = ctx._root()
    _build(ctx, result, None)
    return result, root

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
    lib, _ = _lib[libname]
    assert key in lib, (key, list(lib.keys())) #library key must be in library
    celltype, checksum, is_buffercell = lib[key]
    assert mandated_celltype is None or mandated_celltype == celltype, (mandated_celltype, celltype)
    c = make_cell(celltype, *args, **kwargs)
    c._prelim_checksum = checksum, True, is_buffercell
    if key not in _cells:
        _cells[key] = set()
    _cells[key].add((c, curr_macro()))
    if boundcell:
        _boundcells.add(c)
    c._lib_path = path
    return c

def lib_has_path(libname, path):
    assert libname in _lib
    #print("lib_has_path", libname, path, path in _lib[libname], _lib[libname])
    return path in _lib[0][libname]

def libcell(path, celltype=None):
    return _libcell(path, celltype)

from .macro_mode import curr_macro
from .context import Context
