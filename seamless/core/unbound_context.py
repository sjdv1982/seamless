import weakref
import copy

from . import SeamlessBase

class DummyTaskManager:
    @staticmethod
    def run_synctasks():
        pass

class UnboundManager:
    _destroyed = False  # remains False
    taskmanager = DummyTaskManager
    def __init__(self, ctx):
        self._ctx = weakref.ref(ctx)
        self._root_ = ctx._root_
        self._registered = set()
        self.commands = []
        self.cells = {}
        self.join_structured_cells = set()

    def register_cell(self, cell):
        self._registered.add(cell)
        self.cells[cell.path] = cell

    def register_structured_cell(self, structured_cell):
        self._registered.add(structured_cell)

    def register_transformer(self, transformer):
        self._registered.add(transformer)

    def register_reactor(self, reactor):
        self._registered.add(reactor)

    def register_macro(self, macro):
        self._registered.add(macro)

    def register_macropath(self, macropath):
        self._registered.add(macropath)

    def set_auth_path(self, *args, **kwargs):
        raise Exception("Cannot set structured cell handle in macro mode")

    def set_cell(self, cell, value):
        assert cell._get_manager() is self
        assert cell in self._registered
        self.commands.append(("set cell", (cell, value)))

    def structured_cell_join(self, sc):
        assert sc in self._registered
        self.join_structured_cells.add(sc)

    def connect(self, source, source_subpath, target, target_subpath):
        from .macro import Path
        if isinstance(source, (Cell, Path)):
            return self.connect_cell(source, source_subpath, target, target_subpath)
        if isinstance(source, (OutputPinBase, EditPinBase)):
            assert source_subpath is None and target_subpath is None
            return self.connect_pin(source, target)
        else:
            raise TypeError(source)

    def connect_cell(self, cell, cell_subpath, other, other_subpath):
        from .macro import Path
        if not isinstance(cell, Path):
            assert cell._get_manager() is self
            assert cell in self._registered
        self.commands.append(("connect cell", (cell, cell_subpath, other, other_subpath)))

    def connect_pin(self, pin, cell):
        assert pin._get_manager() is self
        assert pin.worker_ref() in self._registered
        self.commands.append(("connect pin", (pin, cell)))

    def bilink(self, cell, other):
        from .macro import Path
        if not isinstance(cell, Path):
            assert cell._get_manager() is self
            assert cell in self._registered
        self.commands.append(("bilink", (cell, other)))

    def set_cell_checksum(self, 
        cell, checksum, initial, from_structured_cell, trigger_bilinks
    ):
        assert cell._get_manager() is self
        assert cell in self._registered
        self.commands.append(
            ("set cell checksum", 
                (cell, checksum, initial, 
                from_structured_cell, trigger_bilinks)
            )
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
                cell, cell_subpath, other, other_subpath = args
                if other is pin:
                    assert other_subpath is None
                    cells.append((cell, cell_subpath))
        elif isinstance(pin, OutputPin):
            for com, args in self.commands:
                if com != "connect pin":
                    continue
                pin2, cell = args
                if pin2 is pin:
                    cells.append((cell, None))
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
    _boundmanager = None    
    _auto = None
    _toplevel = False
    _naming_pattern = "ctx"    
    _bound = None
    _context = None
    _realmanager = None

    def __init__(
        self, *, 
        root=None,
        toplevel=False,
        macro=False,
        manager=None,
    ):
        from .macro_mode import curr_macro
        super().__init__()
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
            root = Context(toplevel=True, manager=manager)
            self._root_ = root
            self._realmanager = UnboundManager(self)
            if manager is not None:                
                root._realmanager = manager
        elif macro:
            assert manager is None
            root = curr_macro()._root()
            assert root is not None
            self._root_ = root
            manager = UnboundManager(self)
            self._realmanager = manager
        else:
            assert manager is None
        if root is None:
            assert not toplevel and not macro
        else:
            assert isinstance(root, Context), root
        self._root_ = root
        if toplevel:
            register_toplevel(self)

    def __setattr__(self, attr, value):
        if self._bound is not None:
            return setattr(self._bound, attr, value)
        if attr.startswith("_") or hasattr(self.__class__, attr):
            return object.__setattr__(self, attr, value)
        assert value is not None
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
        classes = (UnboundContext, Worker, Cell, UniLink, StructuredCell)
        assert isinstance(child, classes), type(child)
        if isinstance(child, UnboundContext):
            assert child._context is None
            child._realmanager = self._realmanager
            child._context = weakref.ref(self)
            child._root_ = self._root_
            child.name = childname
            self._children[childname] = child
            for subchildname, subchild in child._children.items():
                subchild._set_context(child, subchildname)
        else:
            self._children[childname] = child
            if self._realmanager is not None:
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
        assert self._realmanager is not None
        return self._realmanager

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
        ctx._mount = copy.deepcopy(self._mount)
        ctxmap = {}
        manager = ctx._get_manager()

        def register(child):
            if not isinstance(child, 
                (Cell, Reactor, Transformer, Macro)
            ):
                return
            assert child in self._realmanager._registered, child
            if isinstance(child, Cell):
                manager.register_cell(child)
            elif isinstance(child, Reactor):
                manager.register_reactor(child)
            elif isinstance(child, Transformer):
                manager.register_transformer(child)
            elif isinstance(child, Macro):
                manager.register_macro(child)

        for childname, child in self._children.items():
            if isinstance(child, UnboundContext):
                bound_ctx = Context()
                bound_ctx._macro = curr_macro()
                child._bound = bound_ctx                
                setattr(ctx, childname, bound_ctx)
                ctxmap[childname] = bound_ctx
        for childname, child in self._children.items():
            if isinstance(child, UnboundContext):
                continue
            else:
                ctx._add_child(childname, child)
                if not isinstance(child, StructuredCell):
                    register(child)
        for childname, child in self._children.items():
            if isinstance(child, UnboundContext):
                bound_ctx = ctxmap[childname]
                if self._realmanager is not child._realmanager:
                    self._realmanager.commands += child._realmanager.commands
                    child._realmanager.commands.clear()
                child._bind_stage1(bound_ctx)                
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
                        cell2, _, _, _, _ = args2
                    else:
                        continue
                    if cell2 == cell:
                        supersede = True
                        break
                if supersede:
                    continue
                manager.set_cell(cell, value)
            elif com == "connect cell":                
                cell, cell_subpath, other, other_subpath = args
                manager.connect(cell, cell_subpath, other, other_subpath)
            elif com == "connect pin":
                pin, cell = args
                manager.connect(pin, None, cell, None)
            elif com == "bilink":
                cell, other = args
                cell.bilink(other)
            elif com == "set cell checksum":
                cell, checksum, initial, from_structured_cell, trigger_bilinks = args
                cell._initial_checksum = None
                manager.set_cell_checksum(
                    cell, checksum, 
                    initial=initial, 
                    from_structured_cell=from_structured_cell,
                    trigger_bilinks=trigger_bilinks
                )
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
            elif isinstance(reg, StructuredCell):
                manager.register_structured_cell(reg)
        ctx._root()._cache_paths()
        self._bind_stage2(ctx._get_manager())
        join_structured_cells = self._realmanager.join_structured_cells
        for reg in self._realmanager._registered:
            if isinstance(reg, StructuredCell):
                if reg in join_structured_cells:
                    reg._join()
    
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

from .unilink import UniLink
from .cell import Cell
from .worker import Worker, InputPinBase, OutputPinBase, EditPinBase
from .transformer import Transformer
from .reactor import Reactor
from .macro import Macro
from .structured_cell import StructuredCell
from .context import Context
from .macro_mode import curr_macro, register_toplevel
from .mount import MountItem, is_dummy_mount
