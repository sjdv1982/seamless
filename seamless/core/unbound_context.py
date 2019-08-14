import weakref
import copy

from . import SeamlessBase

class DummyTaskManager:
    @staticmethod
    def run_synctasks():
        pass

class UnboundManager:
    taskmanager = DummyTaskManager
    def __init__(self, ctx):
        self._ctx = weakref.ref(ctx)
        self._registered = set()
        self.commands = []
        self.cells = {}

    def register_cell(self, cell):
        self._registered.add(cell)
        self.cells[cell.path] = cell

    def register_structured_cell(self, structured_cell):
        pass # no-op

    def register_transformer(self, transformer):
        self._registered.add(transformer)

    def register_reactor(self, reactor):
        self._registered.add(reactor)

    def register_macro(self, macro):
        self._registered.add(macro)

    def register_macropath(self, macropath):
        self._registered.add(macropath)

    def set_cell(self, cell, value):
        assert cell._get_manager() is self
        assert cell in self._registered
        self.commands.append(("set cell", (cell, value)))

    def connect(self, source, source_subpath, target, target_subpath):
        from .macro import Path
        if isinstance(source, (Cell, Path)) and source_subpath is None:
            return self.connect_cell(source, target, None)
        if isinstance(source, (OutputPinBase, EditPinBase)) and source_subpath is None:
            return self.connect_pin(source, target)
        else:
            raise NotImplementedError # livegraph branch

    def connect_cell(self, cell, other, cell_subpath):
        from .macro import Path
        if not isinstance(cell, Path):
            assert cell._get_manager() is self
            assert cell in self._registered
        self.commands.append(("connect cell", (cell, other, cell_subpath)))

    def connect_pin(self, pin, cell):
        assert pin._get_manager() is self
        assert pin.worker_ref() in self._registered
        self.commands.append(("connect pin", (pin, cell)))

    def set_cell_checksum(self, cell, checksum, initial, is_buffercell):
        assert cell._get_manager() is self
        assert cell in self._registered
        self.commands.append(
            ("set cell checksum", (cell, checksum, initial, is_buffercell))
        )

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
                cell, other, cell_subpath = args
                if other is pin:
                    cells.append((cell, cell_subpath))
        elif isinstance(pin, OutputPin):
            for com, args in self.commands:
                if com != "connect pin":
                    continue
                pin2, cell, cell_subpath = args
                if pin2 is pin:
                    cells.append((cell, cell_subpath))
        else:
            raise TypeError(pin)
        if isinstance(pin, InputPin):
            return cells[0] if len(cells) else None
        else:
            return cells

    def destroy(self, from_del):
        pass

class UnboundContext(SeamlessBase):

    _name = None
    _children = {}
    _manager = None    
    _auto = None
    _toplevel = False
    _naming_pattern = "ctx"    
    _bound = None
    _context = None

    def __init__(
        self, *, 
        root=None,
        toplevel=False,
        macro=False,
        manager=None,
    ):
        super().__init__()
        if toplevel:
            self._realmanager = UnboundManager(self)
        self._toplevel = toplevel
        if toplevel:
            self._bound_manager = manager
        self._auto = set()
        self._children = {}
        self._mount = None
        self._is_macro = macro
        if toplevel:
            assert root is None
            assert not macro
            root = Context(toplevel=True)
            if manager is not None:                
                root._realmanager = manager
        elif macro:
            assert manager is None
            manager = UnboundManager(self)
            self._realmanager = manager
        else:
            assert manager is None
        self._root_ = root
        if toplevel:
            register_toplevel(self)

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

    def _set_context(self, ctx):
        assert isinstance(ctx, Context) #unbound

    def _add_child(self, childname, child):
        assert isinstance(child, (UnboundContext, Worker, Cell, Link, StructuredCell))
        if isinstance(child, UnboundContext):
            assert child._context is None
            child._realmanager = self._realmanager
            child._context = weakref.ref(self)
            child._root_ = self._root()
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
        if self._bound:
           return self._bound._get_manager()
        if self._toplevel or self._is_macro:
            assert self._realmanager is not None
            return self._realmanager
        else:
            return self._root_._realmanager

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
    def _macro(self):
        if not self._bound:
            return curr_macro()
        else:
            return self._bound._macro

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

    def _root(self):
        return self._root_

    def _bind_stage1(self, ctx):
        from .context import Context
        ctx._mount = copy.deepcopy(self._mount)
        ctxmap = {}
        manager = ctx._get_manager()
        for childname, child in self._children.items():
            if isinstance(child, UnboundContext):
                bound_ctx = Context()
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
                if self._realmanager is not child._realmanager:
                    self._realmanager.commands += child._realmanager.commands
                    child._realmanager.commands.clear()
                child._bind_stage1(bound_ctx)                
            else:
                continue
        ctx._auto = self._auto
        self._bound = ctx        

    def _bind_stage2(self, manager):
        macro = self._macro
        for childname, child in self._children.items():
            if isinstance(child, StructuredCell):
                manager.register_structured_cell(child)
            else:
                continue
        for comnr, (com, args) in enumerate(self._realmanager.commands):            
            if com == "set cell":                
                cell, value = args
                supersede = False
                for com2, args2 in self._realmanager.commands[comnr+1:]:
                    if com2 == "set cell":         
                        cell2, _ = args2
                    elif com2 == "set cell checksum":
                        cell2, _ = args2
                    else:
                        continue
                    if cell2 == cell:
                        supersede = True
                        break
                if supersede:
                    continue
                manager.set_cell(cell, value)
            elif com == "connect cell":                
                cell, other, cell_subpath = args
                manager.connect(cell, None, other, cell_subpath)
            elif com == "connect pin":
                pin, cell = args
                manager.connect(pin, None, cell, None)
            elif com == "set cell checksum":
                cell, checksum, initial, is_buffercell = args
                cell._prelim_checksum = None
                manager.set_cell_checksum(
                    cell, checksum, initial, is_buffercell
                )
                monitor = cell._monitor
                if monitor is not None:  
                    buffer_item = manager.get_value_from_checksum(checksum)
                    if buffer_item is not None:
                        _, _, buffer = buffer_item
                        accessor = manager.get_default_accessor(cell)
                        expression = accessor.to_expression(checksum)
                        value, _ = manager.cache_expression(expression, buffer)
                        monitor.set_path((), value)
            else:
                raise ValueError(com)

    def _bind(self, ctx):
        from .context import Context
        from .macro import Path
        if ctx._toplevel:       
            assert self._toplevel        
        self._bind_stage1(ctx)
        manager = ctx._get_manager()
        for reg in self._realmanager._registered:
            if isinstance(reg, Path):
                manager.register_macropath(reg)
        ctx._root()._cache_paths()
        self._bind_stage2(ctx._get_manager())
    
    def destroy(self, *, from_del=False):
        if self._bound:
            return self._bound.destroy(from_del=from_del)
        for childname, child in self._children.items():
            child.destroy(from_del=from_del)


    def __str__(self):
        if self._bound:
            return str(self._bound)
        else:
            ret = "Seamless unbound context: " + self._format_path()
            return ret

    def __dir__(self):
        if self._bound:
            return dir(self._bound)
        else:
            return super().__dir__()

from .link import Link
from .cell import Cell
from .worker import Worker, InputPinBase, OutputPinBase, EditPinBase
from .structured_cell import StructuredCell
from .context import Context
from .macro_mode import curr_macro, register_toplevel
from .mount import MountItem, is_dummy_mount
