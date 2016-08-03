"""Module for Context class."""

class Context:
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

    class ContextConstructor:
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
                    if not isinstance(
                        cell_or_process, (capturing_class, Context)
                    ):
                        raise TypeError("""
Cannot construct attribute '%s' of subcontext '%s': \
attribute must be an instance of %s" %""" % (self.name, self.parent._name,
                                             capturing_class.__name__)
                                        )
            else:
                cell_or_process = constructor(*args, **kwargs)
            self.parent._add_child(self.name, cell_or_process)
            return cell_or_process

    def __init__(
        self,
        name=None,
        parent=None,
        default_naming_pattern=None,
        constructor=None,
        capturing_class=None
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
        self._children = {}
        if parent is not None:
            self._manager = parent._manager
        else:
            from .process import Manager
            self._manager = Manager()

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
            child.set_context(self)
            
    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        if attr in self._subcontexts:
            raise AttributeError(
             "Cannot assign to subcontext ''%s'" % attr
            )
        self._children[attr] = value

    def __getattr__(self, attr):
        if attr in self._subcontexts:
            return self._subcontexts[attr]
        elif attr in self._children:
            return self._children[attr]
        else:
            return self.ContextConstructor(self, attr)

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

from .cell import Cell, cell, pythoncell
from .process import Process

register_subcontext(
  "processes", "process",
  capturing_class=Process,
  constructor=None,
)
register_subcontext(
  "cells", "cell",
  capturing_class=Cell,
  constructor=cell,
)
register_subcontext(
  "cells.python", "pythoncell",
  capturing_class=None,
  constructor=pythoncell,
)


def context():
    """Return a new Context object."""
    ctx = Context()

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
