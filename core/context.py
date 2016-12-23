"""Module for Context class."""
from weakref import WeakValueDictionary
from .cell import Cell, CellLike, ExportedCell
from .process import Process, ProcessLike, InputPinBase, ExportedInputPin, \
 OutputPinBase, ExportedOutputPin

_active_context = None

#TODO: re-think the concept of capturing classes.
#  Anyway, capturing does not work well for Context (which is CellLike AND ProcessLike)

#TODO: deletion of subcontexts deletes all their connections

def set_active_context(ctx):
    global _active_context
    assert ctx is None or isinstance(ctx, Context)
    _active_context = ctx

def get_active_context():
    return _active_context


class _ContextConstructor:
    def __init__(self, parent, name):
        self.parent = parent
        self.name = name

    def __getattr__(self, attr):
        raise AttributeError(self.name)

    def __call__(self, *args, **kwargs):
        constructor = self.parent._constructor
        if constructor is None:
            if len(args) != 1 or len(kwargs) > 0:
                raise TypeError("""
Cannot construct attribute '%s' of subcontext '%s':
subcontext has no constructor""" %      (self.name, self.parent._name)
                                )
            else:
                cell_or_process = args[0]
                capturing_class = self.parent._capturing_class
                if capturing_class is not None:
                    if not isinstance(
                        cell_or_process, (capturing_class, Context)
                    ):
                        raise TypeError("""
    Cannot construct attribute '%s' of subcontext '%s': \
    attribute must be an instance of %s""" % (self.name, self.parent._name,
                                             capturing_class.__name__)
                                        )
        else:
            cell_or_process = constructor(*args, **kwargs)
        self.parent._add_child(self.name, cell_or_process)
        return cell_or_process

class Context(CellLike, ProcessLike):
    """Context class. Organizes your cells and processes hierchically.

    (Sub)contexts provide a convenient way to manage cells or processes of a
     certain type.
    For example, the "processes" subcontext captures all processes that are
     constructed within the parent context:

    >>> from seamless import context
    >>> ctx = context()
    >>> process = my_process().set_context(ctx)
    >>> ctx.processes.keys()
    ["process1"]
    >>> process is ctx.processes.process1
    True

    myprocess ends up in ctx.processes because "processes" was registered
     with capturing_class "Process" (of which myprocess is an instance)
    If not specified, the capturing class is inherited from the parent
    Subcontexts will only capture from the parent is the capturing class
     is different

    The name 'process1' is automatically generated
     based on the 'default_naming_pattern' parameter

    In addition, cell subcontexts are also useful in constructing cells.
    For example, the "cells.python" automatically construct Python cells.
    Therefore, instead of this:

    >>> from seamless import pythoncell, context
    >>> ctx = context()
    >>> my_pythoncell = pythoncell().set("return 'spam'").set_context(ctx)

    you can also do this:

    >>> from seamless import pythoncell, context
    >>> ctx = context()
    >>> my_pythoncell = ctx.cells.python.my_pythoncell().set("return 'spam'")

    my_pythoncell is automatically constructed using pythoncell, because
     pythoncell was set as the constructor of cells.python

    """

    _name = None
    _parent = None
    _registrar = None
    _like_cell = False          #can be set to True by export
    _like_process = False       #can be set to True by export
    _parent = None
    _default_naming_pattern = None
    _constructor = None
    _capturing_class = None
    _subcontexts = None
    _children = None
    _childids = None
    _manager = None
    registrar = None
    _pins = None

    def __init__(
        self,
        name=None,
        parent=None,
        default_naming_pattern=None,
        constructor=None,
        capturing_class=None,
        active_context=True,
    ):
        """Construct a new context.

        Args:
            parent (optional): parent context
            constructor (optional): function that returns a cell or process
                Allows syntactic sugar to construct cells/processes like this:
                    >>> context.foo(args)
                which is equivalent to:
                    >>> context.foo = constructor(args)
                    >>> context.foo.set_context(context)
            capturing_class: if defined, captures
                all instances of capturing_class from the parent context
                and stores them here
            active_context (default: True): Sets the newly constructed context
                as the active context. Subcontexts constructed by macros are
                automatically parented to the active context
        """
        n = name
        if parent is not None and parent._name is not None:
            n = parent._name + "." + str(n)
        self._name = name
        self._parent = parent
        self._default_naming_pattern = default_naming_pattern
        self._constructor = constructor
        if capturing_class is None and parent is not None:
            capturing_class = parent._capturing_class
        self._capturing_class = capturing_class
        self._subcontexts = {}
        self._pins = {}
        self._children = {}
        self._childids = WeakValueDictionary()
        if parent is not None:
            self._manager = parent._manager
        else:
            from .process import Manager
            self._manager = Manager()
        if active_context:
            set_active_context(self)
        from .registrar import RegistrarAccessor
        self.registrar = RegistrarAccessor(self)

    _dir = ["root", "define", "export", "registrar"]

    def __dir__(self):
        return list(self._subcontexts.keys()) + list(self._children.keys()) \
         + self._dir

    def _add_subcontext(self, subcontext_name, subcontext):
        assert subcontext_name not in self._subcontexts, subcontext_name
        self._subcontexts[subcontext_name] = subcontext

    def _add_child(self, childname, child):
        if childname in self._subcontexts:
            raise AttributeError(
             "Cannot assign to subcontext ''%s'" % childname
            )
        for subcontext in self._subcontexts.values():
            if subcontext._capturing_class == self._capturing_class:
                continue
            if isinstance(child, subcontext._capturing_class):
                subcontext._add_child(childname, child)
        else:
            self._children[childname] = child
            self.root()._childids[id(child)] = child
            child.set_context(self)

    def __setattr__(self, attr, value):
        if hasattr(self.__class__, attr):
            return object.__setattr__(self, attr, value)
        if attr in self._subcontexts:
            raise AttributeError(
             "Cannot assign to subcontext ''%s'" % attr
            )
        if self._capturing_class is None and isinstance(value, Context):
            assert value._parent is self, attr
        self._children[attr] = value

    def __getattr__(self, attr):
        if attr in self._subcontexts:
            return self._subcontexts[attr]
        elif attr in self._children:
            return self._children[attr]
        elif attr in self._pins:
            return self._pins[attr]
        elif attr.startswith("_"):
            raise AttributeError(attr)
        else:
            return _ContextConstructor(self, attr)

    def _hasattr(self, attr):
        if hasattr(self.__class__, attr):
            return True
        if attr in self._subcontexts:
            return True
        if attr in self._children:
            return True
        if attr in self._pins:
            return True
        return False

    def root(self):
        if self._parent is None:
            return self
        else:
            return self._parent.root()

    def define(self, *args, **kwargs):
        if self._constructor is None:
            raise TypeError("""
Cannot define new attribute of subcontext '%s':
subcontext has no constructor""" % self._name
                            )
        cell = self._constructor(*args, **kwargs)


        assert self._default_naming_pattern is not None
        n = 0
        while 1:
            n += 1
            childname = self._default_naming_pattern + str(n)
            if childname not in self._children:
                break
        self._add_child(childname, cell)
        return cell

    def export(self, attr, forced=[]):
        """Exports all unconnected inputs and outputs of a child

        If the child is a cell (or cell-like context):
            - export the child's input as primary input (if unconnected)
            - export the child's output as primary output (if unconnected)
            - export any other pins, if forced
            - sets the context as cell-like
        If the child is a process (or process-like context):
            - export all unconnected input and output pins of the child
            - export any other pins, if forced
            - sets the context as process-like

        Arguments:

        attr: attribute name of the child
        forced: contains a list of pin names that are exported in any case
          (even if not unconnected).
          Use "_input" and "_output" to indicate primary cell input and output

        """
        child = self._children[attr]
        mode = None
        if isinstance(child, CellLike) and child._like_cell:
            mode = "cell"
            pins = ["_input", "_output"]
        elif isinstance(child, ProcessLike) and child._like_process:
            mode = "process"
            pins = child._pins.keys()
        else:
            raise TypeError(child)

        def is_connected(pinname):
            if isinstance(child, CellLike) and child._like_cell:
                child2 = child
                if not isinstance(child, Cell):
                    child2 = child.get_cell()
                if pinname == "_input":
                    return (child2._incoming_connections > 0)
                elif pinname == "_output":
                    return (child2._outgoing_connections > 0)
                else:
                    raise ValueError(pinname)
            else:
                pin = child._pins[pinname]
                if isinstance(pin, InputPinBase):
                    manager = pin._get_manager()
                    con_cells = manager.pin_to_cells.get(pin.get_pin_id(), [])
                    return (len(con_cells) > 0)
                elif isinstance(pin, OutputPinBase):
                    return (len(pin.get_pin()._cell_ids) > 0)
                else:
                    raise TypeError(pin)
        pins = [p for p in pins if not is_connected(p)] + forced
        if not len(pins):
            raise Exception("Zero pins to be exported!")
        for pinname in pins:
            if self._hasattr(pinname):
                raise Exception("Cannot export pin '%s', context has already this attribute" % pinname)
            if isinstance(child, CellLike) and child._like_cell:
                if not isinstance(child, Cell):
                    child = child.get_cell()
                    self._pins[pinname] = ExportedCell(child)
            else:
                pin = child._pins[pinname]
                if isinstance(pin, InputPinBase):
                    self._pins[pinname] = ExportedInputPin(pin)
                elif isinstance(pin, OutputPinBase):
                    self._pins[pinname] = ExportedOutputPin(pin)

        if mode == "cell":
            self._like_cell = True
        elif mode == "process":
            self._like_process = True

_registered_subcontexts = {}


def register_subcontext(
 subcontext_name,
 default_naming_pattern,
 constructor=None,
 capturing_class=None,
):
    """Register a new subcontext.

    After invoking this function, a corresponding subcontext will
     automatically be created whenever a top-level context is created

    subcontext_name can be any unique string.
    A subcontext can be part of another subcontext.
    This can be indicated with dots in subcontext_name (e.g. "cells.python")
    """
    assert subcontext_name not in _registered_subcontexts, subcontext_name

    # If the name contains dots, it has a parent subcontext
    # In that case, check if the parents exists
    # (parents of parents exist by necessity,unless something has been removed)
    pos = subcontext_name.rfind(".")
    if pos > -1:
        parent_ctx_name = subcontext_name[:pos]
        assert parent_ctx_name in _registered_subcontexts, parent_ctx_name

    assert isinstance(default_naming_pattern, str), default_naming_pattern
    assert constructor is None or callable(constructor)
    _registered_subcontexts[subcontext_name] = \
        (default_naming_pattern, constructor, capturing_class)

from .cell import cell, pythoncell

register_subcontext(
  "processes", "process",
  #capturing_class=ProcessLike,
  constructor=None,
)
register_subcontext(
  "cells", "cell",
  #capturing_class=CellLike,
  constructor=cell,
)
"""
register_subcontext(
  "cells.python", "pythoncell",
  capturing_class=None,
  constructor=pythoncell,
)
"""

def context(**kwargs):
    """Return a new Context object."""
    ctx = Context(**kwargs)

    # Get a list of sorted subcontexts
    def sorter(subcontext):
        name = subcontext[0]
        if name is None:
            return 0
        return name.count(".") + 1
    subcontexts = sorted(list(_registered_subcontexts.items()), key=sorter)

    subconts = {}
    for name, (naming_pattern, constructor, class_) in subcontexts:
        parent = ctx
        pos = name.rfind(".")
        if pos > -1:
            parent = subconts[name[:pos]]
        subctx = Context(
            parent=parent,
            name=name,
            default_naming_pattern=naming_pattern,
            constructor=constructor,
            capturing_class=class_
        )
        ctx._add_subcontext(name, subctx)
        subconts[name] = subctx

    return ctx
