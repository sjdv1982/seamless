import weakref
import copy

from . import SeamlessBase
from .macro_mode import curr_macro, toplevel_register
from .mount import MountItem, is_dummy_mount

class UnboundManager:
    def __init__(self, ctx):
        self._ctx = weakref.ref(ctx)
        self._registered = set()
        self.commands = []
        self.cells = {}

    def register_cell(self, cell):
        self._registered.add(cell)
        self.cells[cell.path] = cell

    def register_transformer(self, transformer):
        self._registered.add(transformer)

    def register_reactor(self, reactor):
        self._registered.add(reactor)

    def register_macro(self, macro):
        self._registered.add(macro)

    def set_cell(self, cell, value, *, from_buffer):
        assert cell._get_manager() is self
        assert cell in self._registered
        self.commands.append(("set cell", (cell, value, from_buffer)))

    def connect_cell(self, cell, other):
        from .macro import Path
        if not isinstance(cell, Path):
            assert cell._get_manager() is self
            assert cell in self._registered
        self.commands.append(("connect cell", (cell, other)))

    def connect_pin(self, pin, cell):
        assert pin._get_manager() is self
        assert pin.worker_ref() in self._registered
        self.commands.append(("connect pin", (pin, cell)))

    def set_cell_checksum(self, cell, checksum):
        assert cell._get_manager() is self
        assert cell in self._registered
        self.commands.append(("set cell checksum", (cell, checksum)))

    def set_cell_label(self, cell, label):
        assert cell._get_manager() is self
        assert cell in self._registered
        self.commands.append(("set cell label", (cell, label)))

    def cell_from_pin(self, pin):
        from .worker import InputPin, OutputPin, EditPin
        worker = pin.worker_ref()
        cells = []
        if worker is None:
            raise ValueError("Worker has died")
        if isinstance(pin, (InputPin, EditPin)):
            for com, args in self.commands:
                if com != "connect cell":
                    continue
                cell, other = args
                if other is pin:
                    cells.append(cell)
        elif isinstance(pin, OutputPin):
            for com, args in self.commands:
                if com != "connect pin":
                    continue
                pin2, cell = args
                if pin2 is pin:
                    cells.append(cell)
        else:
            raise TypeError(pin)
        if isinstance(pin, InputPin):
            return cells[0] if len(cells) else None
        else:
            return cells



class UnboundContext(SeamlessBase):

    _name = None
    _children = {}
    _manager = None    
    _auto = None
    _toplevel = False
    _naming_pattern = "ctx"    
    _bound = None

    def __init__(
        self, *,
        name=None,
        toplevel=False
    ):
        super().__init__()
        self._manager = UnboundManager(self)
        self._name = name
        self._toplevel = toplevel
        self._auto = set()
        self._children = {}
        self._mount = None
        if toplevel:
            toplevel_register.add(self)

    def __setattr__(self, attr, value):
        if self._bound is not None:
            return setattr(self._bound, attr, value)
        if attr.startswith("_") or hasattr(self.__class__, attr):
            return object.__setattr__(self, attr, value)
        if attr in self._children and self._children[attr] is not value:
            raise AttributeError(
             "Cannot assign to child '%s'" % attr)
        self._add_child(attr, value)

    def __getattr__(self, attr):
        if self._bound is not None:
            return getattr(self._bound, attr)
        if attr in self._children:
            return self._children[attr]
        raise AttributeError(attr)

    def _add_child(self, childname, child):
        assert isinstance(child, (UnboundContext, Worker, Cell, Link, StructuredCell))
        if isinstance(child, UnboundContext):
            assert child._context is None
            self._children[childname] = child
        else:
            self._children[childname] = child
            child._set_context(self, childname)

    def _add_new_cell(self, cell):
        assert isinstance(cell, Cell)
        assert cell._context is None
        count = 0
        while 1:
            count += 1
            cell_name = "cell" + str(count)
            if not cell_name in self._children:
                break
        self._auto.add(cell_name)
        self._add_child(cell_name, cell)
        return cell_name

    def _get_manager(self):
        return self._manager

    def mount(self, path=None, mode="rw", authority="cell", persistent=False):
        """Performs a "lazy mount"; context is mounted to the directory path when macro mode ends
        path: directory path (can be None if an ancestor context has been mounted)
        mode: "r", "w" or "rw" (passed on to children)
        authority: "cell", "file" or "file-strict" (passed on to children)
        persistent: whether or not the directory persists after the context has been destroyed
                    The same setting is applied to all children
                    May also be None, in which case the directory is emptied, but remains
        """
        assert self._mount is None #Only the mountmanager may modify this further!
        self._mount = {
            "autopath": False,
            "path": path,
            "mode": mode,
            "authority": authority,
            "persistent": persistent
        }
        MountItem(None, self, dummy=True, **self._mount) #to validate parameters

    @property
    def _mount(self):
        if not self._bound:
            return self.__dict__["_mount"]
        else:
            return self._bound._mount
    @_mount.setter
    def _mount(self, value):
        if not self._bound:
            self.__dict__["_mount"] = value
        else:
            self._bound._mount = value

    def _bind_stage1(self, ctx):
        from .context import Context
        ctx._mount = copy.deepcopy(self._mount)
        ctxmap = {}        
        for childname, child in self._children.items():
            if isinstance(child, UnboundContext):
                bound_ctx = Context(name=self._name)
                bound_ctx._macro = curr_macro()
                setattr(ctx, childname, bound_ctx)
                ctxmap[childname] = bound_ctx
        for childname, child in self._children.items():
            if isinstance(child, UnboundContext):
                continue
            else:
                setattr(ctx, childname, child)
        for childname, child in self._children.items():
            if isinstance(child, UnboundContext):
                bound_ctx = ctxmap[childname]
                self._manager.commands += child._manager.commands
                child._bind_stage1(bound_ctx)                
            else:
                continue     
        ctx._auto = self._auto
        self._bound = ctx

    def _bind_stage2(self, manager):
        from .macro import Path
        for com, args in self._manager.commands:
            if com == "set cell":
                cell, value, from_buffer = args
                manager.set_cell(cell, value, from_buffer=from_buffer)
            elif com == "connect cell":
                cell, other = args
                if isinstance(cell, Path):
                    cell = cell._cell
                    if cell is None:
                        continue           
                if isinstance(other, Path):
                    other = other._cell
                    if other is None:
                        continue           
                manager.connect_cell(cell, other)
            elif com == "connect pin":
                pin, cell = args
                manager.connect_pin(pin, cell)
            elif com == "set cell checksum":
                cell, checksum = args
                manager.set_cell_checksum(cell, checksum)
            elif com == "set cell label":
                cell, label = args
                manager.set_cell_label(cell, label)
            else:
                raise ValueError(com)
        manager.schedule_jobs()

    def _bind(self, ctx):
        from .context import Context        
        assert self._toplevel == ctx._toplevel
        self._bind_stage1(ctx)
        ctx._cache_paths()
        self._bind_stage2(ctx._get_manager())
    
    def destroy(self, *, from_del=False):
        for childname, child in self._children.items():
            child.destroy(from_del=from_del)

    """
    def _cache_paths(self):
        for child in self._children.values():
            child._cached_path = None
            child._cached_path = child.path
            if isinstance(child, UnboundContext):
                child._cache_paths()
    """

from .link import Link
from .cell import Cell
from .worker import Worker, InputPinBase, OutputPinBase, EditPinBase
from .structured_cell import StructuredCell
