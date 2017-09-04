import weakref
from enum import Enum

class IpyString(str):
    def _repr_pretty_(self, p, cycle):
        return p.text(str(self))

class SeamlessBase:
    _destroyed = False
    _macro_object = None # macro object that CREATED this instance
    _context = None
    _last_context = None
    name = None

    StatusFlags = Enum('StatusFlags', ('OK', 'PENDING', 'UNDEFINED', 'UNCONNECTED', 'ERROR'))
    _status = StatusFlags.UNDEFINED

    def __init__(self):
        self._owned = []
        self._owner = None

    @property
    def path(self):
        if self._context is None:
            return ()
        elif self._context.path is None:
            return ("<None>", self.name)
        else:
            return self._context.path + (self.name,)

    def _validate_path(self, required_path=None):
        if required_path is None:
            required_path = self.path
        else:
            assert self.path == required_path, (self.path, required_path)
        return required_path

    def _find_successor(self):
        path = list(self.path)
        p = self
        subpath = []
        ok = False
        while p._destroyed:
            if not len(path):
                break
            p = p._last_context
            if p is None:
                break
            subpath = [path.pop(-1)] + subpath
        if p is None:
            return None
        if not p._destroyed:
            for subp in subpath:
                try:
                    p = getattr(p, subp)
                    assert not p._destroyed
                except Exception:
                    break
            else:
                ok = True
        if ok:
            return p

    def _set_context(self, context, name, force_detach=False):
        from .context import Context
        assert isinstance(context, Context)
        if self._context is not None:
            assert self.name is not None
            if context is not self._context or force_detach:
                childname = self.name
                assert self._context._children[childname] is self
                self._context._children.pop(childname)
                if childname in self._context._auto:
                    self._context._auto.remove(childname)
        if context is not None:
            self._last_context = context
        self._context = context
        self.name = name
        return self

    @property
    def context(self):
        return self._context

    def own(self, obj):
        """Gives ownership of another construct "obj" to this construct.
        If this construct is destroyed, so is "obj"."""
        from .cell import Cell
        from .context import Context
        from .worker import Worker
        from .macro import get_macro_mode
        assert isinstance(obj, (Cell, Worker, Context)), type(obj)
        assert obj is not self
        if self._owner is not None:
            owner = self._owner()
            if owner is not None:
                exc = "{0} cannot own, it is already owned by {1}"
                raise Exception(exc.format(self, owner))
            self._owner = None
        if obj not in self._owned:
            self._owned.append(obj)
            if obj._owner is not None:
                owner = obj._owner()
                if owner is not None:
                    if obj in owner._owned:
                        owner._owned.remove(obj)
            obj._owner = None
            macro_control = self._macro_control()
            if not get_macro_mode() and \
              macro_control is not None and macro_control is not obj._macro_control():
                macro_cells = macro_control._macro_object.cell_args.values()
                macro_cells = sorted([c.format_path() for c in macro_cells])
                macro_cells = "\n  " + "\n  ".join(macro_cells)
                if macro_control is self:
                    print("""***********************************************************************************************************************
WARNING: {0} is now owned by {1}, which is under live macro control.
The macro is controlled by the following cells: {2}
When any of these cells change and the macro is re-executed, the owned object will be deleted and likely not re-created
***********************************************************************************************************************"""\
                    .format(obj, self, macro_cells))
                elif macro_control is not None:
                    print("""***********************************************************************************************************************
WARNING: {0} is now owned by {1}, which is a child of, or owned by, {2}, which is under live macro control.
The macro is controlled by the following cells: {3}
When any of these cells change and the macro is re-executed, the owned object will be deleted and likely not re-created
***********************************************************************************************************************"""\
                    .format(obj, self, macro_control, macro_cells))
            obj._owner = weakref.ref(self)

    def _owns_all(self):
        owns = set(self._owned)
        for owned in self._owned:
            owns.update(owned._owns_all())
        return owns

    def _macro_control(self, include_owner=False, primary=True, done=None):
        if self._macro_object is not None:
            return self
        if done is None:
            done = []
        if self in done:
            msg = "Ownership circle:\n    " + "\n    ".join([x.format_path() for x in done])
            raise Exception(msg)
        done.append(self)

        ret = None
        if self.context is not None:
            ret = self.context._macro_control(include_owner, False, done)
        if ret is not None:
            return ret
        if include_owner:
            if self._owner is not None:
                owner = self._owner()
                if owner is not None:
                    ret = owner._macro_control(True, False)
                    if ret is not None:
                        return ret
        elif primary:
            return self._macro_control(True, True)
        else:
            return None


    def destroy(self):
        """Removes the construct from its parent context"""
        if self._destroyed:
            return
        self._destroyed = True
        #print("DESTROY", self)
        ctx = self._context
        if ctx is not None:
            for childname, child in ctx._children.items():
                if child is self:
                    ctx._children.pop(childname)
                    break
            ctx._manager.unstable_workers.discard(self)
        for obj in self._owned:
            obj.destroy()


    def format_path(self):
        if self.path is None:
            ret = "<None>"
        else:
            ret = "." + ".".join(self.path)
        if self._owner is not None:
            owner = self._owner()
            if owner is not None:
                ret += ", owned by " + owner.format_path()
        return ret

    def __str__(self):
        ret = "Seamless object: " + self.format_path()
        return ret

    def __repr__(self):
        return self.__str__()

    @property
    def macro(self):
        """Returns the macro object associated with this construct"""
        return self._macro_object
    def _set_macro_object(self, macro_object):
        self._macro_object = macro_object

    def __del__(self):
        #print("__del__", type(self), self.path, self._destroyed)
        try:
            self.destroy()
        except Exception:
            pass

class Managed(SeamlessBase):
    def _get_manager(self):
        context = self.context
        if context is None:
            raise Exception(
             "Cannot carry out requested operation without a context"
            )
        return context._manager

from .cell import Cell
from .worker import Worker
from .context import Context
