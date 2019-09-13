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

_updating = False

def _update_old_keys(libname, oldkeys, oldlib, lib, old_root, root):
    """
    Updates existing libcells with the new library:
    - Destroy any libcell under macro control, and instruct its macro to re-execute
    - For any libcell not under macro control, update its checksum
    """
    from .manager.tasks.macro_update import MacroUpdateTask
    cachemanager = root._get_manager().cachemanager
    old_cachemanager = old_root._get_manager().cachemanager
    global _updating
    assert not _updating
    assert not macro_mode.get_macro_mode()
    macros_to_update = set()
    for key in oldkeys:
        if (libname, key) not in _cells:
            continue
        oldcells = _cells[libname, key]
        for oldcell, macro in oldcells.items():
            assert oldcell._lib_path == (libname, key), (oldcell, oldcell._lib_path)
            if macro is None:
                continue
            if oldcell._destroyed:
                print("Warning: destroyed libcell is still registered ", libname, key, oldcell)
                continue
            macros_to_update.add(macro)
            
    try:
        macro_mode._macro_mode = True # to halt all MacroUpdateTasks

        for macro in macros_to_update:
            if macro._destroyed:
                continue
            manager = macro._get_manager()
            manager.cancel_macro(macro, False)
            # Above should destroy all oldcells belonging to the macro            
            MacroUpdateTask(manager, macro).launch()

        _updating = True        
        for key in oldkeys:
            if (libname, key) not in _cells:
                continue
            oldcells = _cells[libname, key]
            for oldcell, macro in oldcells.items():
                assert oldcell._lib_path == (libname, key), (oldcell, oldcell._lib_path)
                if oldcell._destroyed:
                    print("Warning: destroyed libcell is still registered ", libname, key, oldcell)
                    continue
                if macro is not None:
                    print("Warning: outdated libcell belongs to a macro that was not canc ", libname, key, oldcell)
                    continue
                exists = False
                if key in lib:
                    celltype, checksum, _ = lib[key]
                    old_celltype, old_checksum, _ = oldlib[key]
                    if old_celltype == celltype:
                        exists = True
                oldmanager = oldcell._get_manager()
                if exists:
                    if old_checksum != checksum:                        
                        cs = checksum.hex() if checksum is not None else None
                        if checksum is not None:
                            propagate_cell(oldmanager.livegraph, oldcell)
                        else:
                            oldmanager.cancel_cell(oldcell, True, StatusReasonEnum.UNDEFINED)
                        oldcell.set_checksum(cs)                        
                else:
                    if oldcell not in _boundcells:
                        print("Warning: Library key '%s' deleted, %s set to None" % (key, oldcell))
                    if old_checksum is not None:
                        oldmanager.cancel_cell(oldcell, True, StatusReasonEnum.UNDEFINED)
                    oldcell.set_checksum(None)
    finally:
        _updating = False
        macro_mode._macro_mode = False

def register(name, lib, root):
    assert not _updating
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
        name,
        oldkeys, oldlib, lib, 
        old_root, root
    )
    unregister(name, pop_keys=False)
    if root not in _root_to_libname:
        _root_to_libname[root] = []
    _root_to_libname[root].append(name)    
    _lib[name] = lib, root

def unregister(name, pop_keys=True):
    assert not _updating
    lib, root = _lib[name]
    cachemanager = root._get_manager().cachemanager
    for key, entry in lib.items():
        _, checksum, _ = entry
        if checksum is None:
            continue
        cachemanager.decref_checksum(checksum, lib, True)
        if pop_keys:
            cells = _cells.pop((name, key), [])
            for cell in cells:
                cell._lib_path = None
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
            if child._structured_cell: raise NotImplementedError  # livegraph branch
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
    assert not _updating
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
    celltype, checksum, from_structured_cell = lib[key]
    assert mandated_celltype is None or mandated_celltype == celltype, (mandated_celltype, celltype)
    c = make_cell(celltype, *args, **kwargs)
    if checksum is not None:
        c._initial_checksum = checksum, True, from_structured_cell
    if (libname, key) not in _cells:
        _cells[libname, key] = {}
    _cells[libname, key][c] = curr_macro()
    if boundcell:
        _boundcells.add(c)
    c._lib_path = libname, key
    return c

def lib_has_path(libname, path):
    raise NotImplementedError ### livegraph branch
    assert libname in _lib
    #print("lib_has_path", libname, path, path in _lib[libname], _lib[libname])
    return path in _lib[libname]

def unregister_libcell(cell):
    assert not _updating
    libname, key = cell._lib_path
    lib = _lib[libname]
    cells = _cells[libname, key]
    cells.pop(cell)



def libcell(path, celltype=None):
    return _libcell(path, celltype)

from . import macro_mode
from .macro_mode import curr_macro
from .context import Context
from .manager.propagate import propagate_cell
from .status import StatusReasonEnum
