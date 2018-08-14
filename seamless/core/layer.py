from .macro_mode import curr_macro, outer_macro, with_macro_mode
from .connection import Connection, CellToCellConnection, CellToPinConnection, \
 PinToCellConnection
import weakref
from weakref import WeakKeyDictionary, WeakValueDictionary

#"macro" must be either a real macro, or a toplevel context

def _get_path(macro):
    if isinstance(macro, Context):
        ctx = macro
        assert ctx._toplevel
        mpath = ()
    else:
        mpath = macro.path + (macro.macro_context_name,)
    return mpath

class Path:
    _path = None
    _relative = False
    macro = None
    def _is_sealed(self):
        return True #paths are always sealed
    def __init__(self, obj=None, force_relative=False):
        if obj is None:
            return
        assert not isinstance(obj, Path)
        path = obj.path
        macro = curr_macro()
        if macro is not None:
            mpath = _get_path(macro)
            if path[:len(mpath)] == mpath:
                self._relative = True
                path = path[len(mpath):]
            elif force_relative:
                str_path =  "." + ".".join(path)
                str_mpath =  "." + ".".join(mpath)
                raise Exception("Path %s goes above current macro %s" % (str_path, str_mpath))
        else:
            macro = obj._root()
            self._relative = None
        self.macro = weakref.ref(macro)
        self._path = path
    def path(self):
        return self._path
    def connect(self, *args, **kwargs):
        assert self.macro is not None
        connect_path(self, *args, **kwargs)
        return self
    def _root(self):
        assert self.macro is not None
        return self.macro()._root()
    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError
        subpath = Path()
        subpath._relative = self._relative
        subpath._path = self._path + (attr,)
        subpath.macro = self.macro
        return subpath
    def __str__(self):
        return "Seamless path: %s" % (".".join(self._path))

class LayeredConnectionPoint:
    static = False
    obj_original = lambda self: None
    obj = None
    def __init__(self, type, path, obj, is_input):
        assert type in ("cell", "pin", "path")
        self.type = type
        assert isinstance(path, Path)
        assert path._relative in (True, None), path._relative
        self.path = path
        self.is_input = is_input
        if obj is not None:
            self.obj_original = weakref.ref(obj)
        if obj is not None:
            self.set_object(obj, from_init=True)
            if not obj._is_sealed():
                self.static = True
        else:
            assert type != "pin"
            self.obj = None

    def set_object(self, obj, from_init=False):
        if self.obj is not None and obj is self.obj():
            return False
        if obj is None:
            self.obj = None
            return False
        assert not self.static
        if isinstance(obj, Link):
            obj = obj.get_linked()
        if self.type == "cell":
            if self.obj_original is None \
              and isinstance(obj, (InputPinBase, OutputPinBase, EditPinBase) ):
                path = "." + ".".join(self.path)
                raise TypeError("Path %s: connections to paths that later resolve to pins are not supported" % path)
            else:
                assert isinstance(obj, CellLikeBase), obj
        elif type == "pin":
            if self.is_input:
                assert isinstance(obj, (OutputPinBase, EditPinBase))
            else:
                assert isinstance(obj, (InputPinBase, EditPinBase))
        else:
            assert isinstance(obj, (CellLikeBase, InputPinBase, OutputPinBase, EditPinBase))
        self.obj = weakref.ref(obj)
        return True

_lc_id = -1
class LayeredConnection:
    def __init__(self, source, target, transfer_mode=None):
        global _lc_id
        assert isinstance(source, LayeredConnectionPoint)
        assert isinstance(target, LayeredConnectionPoint)
        self.source = source
        self.target = target
        self.transfer_mode = transfer_mode
        macro = curr_macro()
        if macro is None:
            macro = source.path.macro()._root()
            assert source.path.macro()._root() == target.path.macro()._root()
        self.macro = weakref.ref(macro)
        self.mode = None #will be ("cell", "cell"), ("pin", "cell") etc. after activation
        self.id = _lc_id
        _lc_id -= 1

    def _get_half_mode(self, lcp):
        obj = lcp.obj()
        assert obj is not None
        if isinstance(obj, CellLikeBase):
            return "cell"
        elif isinstance(obj, (InputPinBase, OutputPinBase, EditPinBase)):
            return "pin"
        else:
            raise TypeError(obj)

    def _activate_cell_cell(self):
        source, target = self.source.obj(), self.target.obj()
        #TODO: negotiate cell-to-cell serialization protocol

        connection = CellToCellConnection(self.id, source, target, self.transfer_mode)

        mgr = target._get_manager()
        mgr.cell_from_cell[target] = connection
        target._authoritative = False

        mgr = source._get_manager()
        if source not in mgr.cell_to_cells:
            mgr.cell_to_cells[source] = []
        ctc = mgr.cell_to_cells[source]
        ctc[:] = [c for c in ctc if c.id != self.id]
        mgr.cell_to_cells[source].append(connection)

        if source._status == CellLikeBase.StatusFlags.OK:
            connection.fire()

    def _activate_cell_pin(self):
        cell, target = self.source.obj(), self.target.obj()
        connection = CellToPinConnection(self.id, cell, target)
        mgr = cell._get_manager()
        if cell not in mgr.cell_to_pins:
            mgr.cell_to_pins[cell] = []
        ctp = mgr.cell_to_pins[cell]
        ctp[:] = [c for c in ctp if c.id != self.id]
        ctp.append(connection)

        mgr = target._get_manager()
        mgr.pin_from_cell[target] = connection

        if cell._status == CellLikeBase.StatusFlags.OK:
            connection.fire()

    def _activate_pin_cell(self):
        pin, target = self.source.obj(), self.target.obj()
        connection = PinToCellConnection(self.id, pin, target)
        mgr = pin._get_manager()
        if pin not in mgr.pin_to_cells:
            mgr.pin_to_cells[pin] = []
        ptc = mgr.pin_to_cells[pin]
        ptc[:] = [c for c in ptc if c.id != self.id]
        ptc.append(connection)

        mgr2 = target._get_manager()
        mgr2.cell_from_pin[target] = connection
        if not isinstance(pin, EditPinBase):
            target._authoritative = False
        worker = pin.worker_ref()
        if pin.last_value is not None:
            mgr.pin_send_update(pin,
                pin.last_value,
                preliminary=pin.last_value_preliminary,
                target=target,
            )

    def activate(self, only_macros):
        from .macro import Macro
        from .macro_mode import curr_macro
        assert self.concrete
        source, target = self.source.obj(), self.target.obj()
        assert source._root() is target._root()
        mode1 = self._get_half_mode(self.source)
        mode2 = self._get_half_mode(self.target)
        self.mode = mode1, mode2
        if (mode1, mode2) == ("cell", "cell"):
            if only_macros:
                return
            self._activate_cell_cell()
        elif (mode1, mode2) == ("cell", "pin"):
            m = target.worker_ref()
            is_macro_target = False
            if isinstance(m, Macro):
                is_macro_target = True
                cm = curr_macro()
                if cm is not None:
                    cpath = cm._context().path + (cm.macro_context_name,)
                    if m.path[:len(cpath)] != cpath:
                        is_macro_target = False
            if only_macros != is_macro_target:
                return
            self._activate_cell_pin()
        elif (mode1, mode2) == ("pin", "cell"):
            if only_macros:
                return
            self._activate_pin_cell()
        else:
            raise ValueError(self.mode)

    def fill_object(self, obj, obj_path):
        success = False
        if self.source.path.path() == obj_path:
            if not self.source.static:
                if self.source.set_object(obj):
                    success = True
        if self.target.path.path() == obj_path:
            if not self.target.static:
                if self.target.set_object(obj):
                    success = True
        if success:
            if self.concrete:
                #self.activate()
                return True

    """ YAGNI?
    def clear_object_path(self, obj_path):
        if self.source.path.path() == obj_path:
            if not self.source.static:
                self.source.set_object(None)
        if self.target.path.path() == obj_path:
            if not self.target.static:
                self.target.set_object(None)
        if not self.concrete:
            self.mode = None
    """
    def clear_object(self, obj):
        if not self.concrete:
            return
        if self.source.obj is not None and self.source.obj() is obj:
            if not self.source.static:
                self.source.set_object(None)
                target = self.target.obj()
                mgr = target._get_manager()
                if isinstance(target, CellLikeBase):
                    target._authoritative = True
                    target.set(None)
                    if isinstance(obj, CellLikeBase):
                        mgr.cell_from_cell.pop(target)
                    elif isinstance(target, OutputPinBase):
                        mgr.cell_from_pin.pop(target)
                elif isinstance(target, (InputPinBase, EditPinBase)):
                    target.receive_update(None, None, None, None)
                    mgr.pin_from_cell.remove(target)
        if self.target.obj is not None and self.target.obj() is obj:
            if not self.target.static:
                self.target.set_object(None)
        if not self.concrete:
            self.mode = None


    @property
    def concrete(self):
        return self.source.obj is not None and self.target.obj is not None

_layers = WeakKeyDictionary()
_id_to_lc = {}

def create_layer(macro):
    assert macro not in _layers, macro
    _layers[macro] = []

def get_layers(macro):
    assert macro in _layers, macro
    layers = {}
    macro_path = macro.path
    for m in _layers:
        mpath = m.path
        if mpath[:len(macro_path)] == macro_path:
            layers[m] = _layers[m]
    return layers

def restore_layers(macro, layers):
    assert macro in _layers, macro
    assert macro in layers, macro
    _layers.update(layers)

def destroy_layer(macro):
    if isinstance(macro, Context) and macro not in _layers:
        return
    assert macro in _layers, macro
    layer = _layers.pop(macro)
    for lc in layer:
        lc2 = _id_to_lc.pop(lc.id)
        assert lc2 is lc, (lc.id, lc2.id, lc, lc2)

def fill_object(obj):
    result = []
    if isinstance(obj, Worker):
        for pin in obj._pins.values():
            result += fill_object(pin)
    path = obj.path
    for id in sorted(list(_id_to_lc.keys())):
        lc = _id_to_lc[id]
        macro = lc.macro()
        if macro is None:
            continue
        mpath = _get_path(macro)
        lc = _id_to_lc[id]
        if path[:len(mpath)] != mpath:
            continue
        relpath = path[len(mpath):]
        filled = lc.fill_object(obj, relpath)
        if filled:
            result.append(lc)
    return result

def fill_objects(ctx, macro):
    """Fills in all the LayeredConnections with paths that point to
     children of ctx
    It doesn't matter what is on the other end of the connection
    (can be a child or a parent of ctx, at any level)
    """
    result = []
    if ctx is None:
        for c in _layers:
            if not isinstance(c, Context):
                continue
            result += fill_objects(c, macro)
        return result
    assert isinstance(ctx, Context)

    #Below is not justified, since one can connect into sealed context, at present
    #To make it work, disallow such connections if they are not exported
    # (and still check exported children for fill_objects)
    ###if ctx._is_sealed():
    ###    return

    # Anyway, it is not so bad, if we fill only when the outermost macro has finished...
    #if outer_macro() is not macro:
    #    return []

    #... but this is *also* not justified! We need to fill in connections early
    # so that we can activate sub-macros early! (while still reorganizing the mount,
    # and before caching)
    # Current workaround: fill in at all macro levels
    # Future solutions:
    # - Don't fill in objects if their seal is deeper than the current macro
    # - Faster connection lookup (slow N(1) now!)

    for child in list(ctx._children.values()):
        if isinstance(child, Context):
            result += fill_objects(child, macro)
        else:
            result += fill_object(child)
    return result

def clear_object(obj):
    if isinstance(obj, Worker):
        for pin in list(obj._pins.values()):
            clear_object(pin)
    path = obj.path
    for id in sorted(list(_id_to_lc.keys())):
        lc = _id_to_lc[id]
        macro = lc.macro()
        if macro is None:
            continue
        mpath = _get_path(macro)
        lc = _id_to_lc[id]
        if path[:len(mpath)] != mpath:
            continue
        lc.clear_object(obj)

def clear_objects(ctx):
    assert isinstance(ctx, Context)
    for child in list(ctx._children.values()):
        if isinstance(child, Context):
            clear_objects(child)
        else:
            clear_object(child)

def fire_connection(id):
    assert id in _id_to_lc
    lc = _id_to_lc[id]
    if lc.concrete:
        lc.fire()

def _add_to_layer(lc):
    """
    print("_add_to_layer")
    print(lc.source.path, lc.target.path)
    print(lc.source.obj, lc.target.obj)
    print(lc.source.static, lc.target.static)
    print()
    """
    assert lc.macro() in _layers, lc.macro()
    _layers[lc.macro()].append(lc)
    _id_to_lc[lc.id] = lc
    return lc.concrete, lc.id

def _lc_target(target, cell=False):
    target0 = target
    if isinstance(target, Link):
        target = target.get_linked()
    if isinstance(target, CellLikeBase):
        type_ = "cell"
    elif isinstance(target, (InputPinBase, OutputPinBase, EditPinBase) ):
        type_ = "pin"
        if cell:
            raise TypeError("Connection target must be a cell; pin-pin connections not allowed")
    else:
        assert isinstance(target0, Path)
        type_ = "path"
        if cell:
            type_ = "cell"
        target = None
    if isinstance(target0, Path):
        path = target0
    else:
        path = Path(target0, force_relative=True)
    return LayeredConnectionPoint(type_, path, target, is_input=False)

def connect_pin(pin, target):
    pin0 = pin
    if isinstance(pin, Link):
        pin = pin.get_linked()
    path = Path(pin0, force_relative=True)
    lc_source = LayeredConnectionPoint("pin", path, pin, is_input=True)
    lc_target = _lc_target(target, cell=True)
    lc = LayeredConnection(lc_source, lc_target)
    return _add_to_layer(lc)

def connect_cell(cell, target, transfer_mode):
    assert cell is not None
    cell0 = cell
    if isinstance(cell, Link):
        cell = cell.get_linked()
    path = Path(cell0, force_relative=True)
    lc_source = LayeredConnectionPoint("cell", path, cell, is_input=True)
    lc_target = _lc_target(target)
    lc = LayeredConnection(lc_source, lc_target, transfer_mode)
    return _add_to_layer(lc)

def connect_path(source, target):
    assert isinstance(source, Path)
    lc_source = LayeredConnectionPoint("path", source, None, is_input=True)
    lc_target = _lc_target(target)
    lc = LayeredConnection(lc_source, lc_target, None)
    return _add_to_layer(lc)

def check_async_macro_contexts(ctx, macro):
    from .macro import Macro
    # For now, do this check only for the outer macro that is being executed
    # I believe this is correct, although it could give some false negatives?
    # Anyway, when extern connections will be supported by caching,
    #  the picture will change a bit
    if outer_macro() is not macro:
        return
    if ctx is None:
        for c in _layers:
            if not isinstance(c, Context):
                continue
            check_async_macro_contexts(c, macro)
        return
    for childname, child in list(ctx._children.items()):
        if child.name.startswith(Macro.macro_tag):
            continue
        if isinstance(child, Context):
            check_async_macro_contexts(child, macro)
        if not isinstance(child, Macro):
            continue
        if child.ctx is None:
            print("Warning: macro %s has asynchronous dependencies, beware of cache misses" % child)
        else:
            check_async_macro_contexts(child.ctx, macro)

@with_macro_mode
def path(obj, *, force_relative=False):
    return Path(obj, force_relative)

from . import Link, CellLikeBase, get_macro_mode
from .context import Context
from .worker import InputPinBase, OutputPinBase, EditPinBase, Worker
from .transformer import Transformer
