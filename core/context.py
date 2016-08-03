"""Module for Context class."""

from .cell import Cell, cell, pythoncell
from .process import Process


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

    def __init__(self, parent=None, constructor=None, capturing_class=None):
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
        self._parent = parent
        self._capturing_class = capturing_class

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
        parent_subcontext_name = subcontext_name[:pos-1]
        assert parent_subcontext_name in _registered_subcontexts, \
            parent_subcontext_name

    assert isinstance(default_naming_pattern, str)
    assert callable(constructor)
    _registered_subcontexts[subcontext_name] = \
        (constructor, capturing_class,
            parent_context_name)


register_subcontext(
  "processes", "process",
  cell_or_process_class=Process,
  cell_constructor=None,
)
register_subcontext(
  "cells", "cell",
  cell_or_process_class=Cell,
  cell_constructor=cell,
)
register_subcontext(
  "cells.python", "pythoncell",
  cell_or_process_class=None,
  cell_constructor=pythoncell,
)


def context():
    """Return a new Context object."""
    cont = Context()

    # Get a list of sorted subcontexts
    def sorter(subcontext):
        name = subcontext[0]
        if name is None:
            return 0
        return name.count(".") + 1
    subcontexts = sorted(list(_registered_subcontexts.values(), key=sorter))

    subcontexts = {}
    for name, constructor, class_ in subcontexts:
        parent = cont
        pos = name.rfind(".")
        if pos > -1:
            parent = subcontexts[name[:pos-1]]
        subcont = Context(parent=parent, )
        subcontexts[name] = subcont

    return cont
