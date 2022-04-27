import weakref
from .Context import Context, SubContext
from .Transformer import Transformer
from .Macro import Macro
from .Cell import Cell
from .Module import Module
from .library.libinstance import LibInstance
from .proxy import Proxy
from .Base import Base
from copy import deepcopy

classes = (Context, SubContext, Transformer, Macro, Cell, Module, LibInstance)
def copy(source, target):

    def get_path(x):
        if isinstance(x, Context):
            return ()
        elif isinstance(x, (Base, LibInstance)):
            return x._path
        elif isinstance(x, Proxy):
            tail = x._path
            return get_path(x._parent()) + tail
        else:
            raise TypeError(x)

    def get_top(x):
        if isinstance(x, Base):
            ctx = x._get_top_parent()
        elif isinstance(x, (Proxy, Libinstance)):
            x0 = x
            while isinstance(x0, Proxy):
                x0 = x0._parent()
            if isinstance(x0, Libinstance):
                ctx = x0._parent()
            else:
                ctx = x0._get_top_parent()
        elif isinstance(x, Libinstance):
            ctx = x._parent()
        return ctx

    if not isinstance(source, classes):
        msg = "Source must be Cell, Context, SubContext, Transformer, Macro, Module or Library, not {}"
        raise TypeError(msg.format(type(source)))
    if not isinstance(target, classes + (Proxy,)):
        msg = "Target must be convertible to a path"

    source_path = get_path(source)
    source_ctx = get_top(source)

    target_path = get_path(target)
    while isinstance(target, Proxy):
        target = target._parent()
    target_ctx = target._get_top_parent()

    if isinstance(source, (Context, SubContext)):
        assign_context(target_ctx, target_path, source)
    elif isinstance(source, (Cell, Transformer, Macro, Module)):
        obj = deepcopy(source)
        obj._path = target_path
        obj._parent = weakref.ref(target_ctx)
        payload = deepcopy(source_ctx._graph[0][source_path])
        payload["path"] = target_path
        target_ctx._set_child(target_path, obj)
        target_ctx._graph[0][target_path] = payload
    elif isinstance(source, LibInstance):
        raise NotImplementedError
    target_ctx.translate()
    
from .assign import assign_context