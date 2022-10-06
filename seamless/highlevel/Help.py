import weakref
from functools import wraps

from seamless.core.macro import Path

from .Cell import Cell
from .SubContext import SubContext

class HelpWrapper:
    def __init__(self, wrapped, sub_path=None):
        if sub_path is None:
            sub_path = ()
        if isinstance(wrapped, SubContext):
            self._wrapped = None
            self._wrapped_path = wrapped._path
            self._wrapped_parent = weakref.ref(wrapped._parent())
        else:
            self._wrapped = weakref.ref(wrapped)
        self._sub_path = sub_path  # within the help context

    def _get_wrapped(self):
        if self._wrapped is None:
            wrapped_parent = self._wrapped_parent()
            if wrapped_parent is None:
                return None
            return SubContext(wrapped_parent, self._wrapped_path)
        else:
            return self._wrapped()

    @property
    def _path(self):
        wrapped = self._get_wrapped()
        return wrapped._path

    @property
    def _help_path(self):
        return ("HELP",) + self._path + self._sub_path

    def _get_ctx(self):
        wrapped = self._get_wrapped()
        if wrapped is None:
            return None
        parent = wrapped._parent()
        if parent is None:
            return None
        return parent._get_top_parent()

    def __str__(self):
        result = "{} for {}".format(type(self).__name__, self._get_wrapped())
        if len(self._sub_path):
            result += ", sub-path ." + ".".join(self._sub_path) 
        return result

    def __repr__(self):
        return str(self)

class HelpCell(HelpWrapper):
        
    @property
    def _index_path(self):        
        return self._help_path + ("INDEX",)

    def _help_index_cell(self, create=False):
        ctx = self._get_ctx()
        if ctx is None:
            if create:
                raise AttributeError
            return None
        help_index_cell = ctx._children.get(self._index_path)
        if create and help_index_cell is None:
            path = self._index_path
            Cell(parent=ctx, path=path) #inserts itself as child
            cell = get_new_cell(path)          
            cell["celltype"] = "text"
            cell["UNTRANSLATED"] = True  
            nodes = ctx._graph[0]
            nodes[path] = cell
            help_index_cell = ctx._children[path]
            for n in range(1, len(self._help_path)+1):
                p = self._help_path[:n]
                if p not in nodes:
                    nodes[p] = {
                        "path": p,
                        "type": "context"
                    }
            ctx._translate()

        return help_index_cell

    @wraps(Cell.set)
    def set(self, value):
        help_index_cell = self._help_index_cell(create=True)
        help_index_cell.set(value)

    @property
    def value(self):
        help_index_cell = self._help_index_cell()
        if help_index_cell is None:
            return None
        hcell = help_index_cell._get_hcell()
        if hcell.get("UNTRANSLATED"):
            return hcell.get("TEMP")
        return help_index_cell.value

    @property
    @wraps(Cell.celltype)
    def celltype(self):
        help_index_cell = self._help_index_cell()
        if help_index_cell is None:
            return None
        return help_index_cell.celltype

    @celltype.setter
    def celltype(self, value):
        help_index_cell = self._help_index_cell()
        if help_index_cell is None:
            raise AttributeError
        help_index_cell.celltype = value

    @property
    @wraps(Cell.mimetype)
    def mimetype(self):
        help_index_cell = self._help_index_cell()
        if help_index_cell is None:
            return None
        return help_index_cell.mimetype

    @mimetype.setter
    def mimetype(self, value):
        help_index_cell = self._help_index_cell()
        if help_index_cell is None:
            raise AttributeError
        help_index_cell.mimetype = value
    
    @wraps(Cell.mount)
    def mount(self, *args, **kwargs):
        help_index_cell = self._help_index_cell(create=True)
        return help_index_cell.mount(*args, **kwargs)

    @wraps(Cell.share)
    def share(self, *args, **kwargs):
        help_index_cell = self._help_index_cell(create=True)
        return help_index_cell.share(*args, **kwargs)

    @wraps(Cell.status)
    def status(self):
        help_index_cell = self._help_index_cell()
        if help_index_cell is None:
            return None
        return help_index_cell.status

    @wraps(Cell.exception)
    def exception(self):
        help_index_cell = self._help_index_cell()
        if help_index_cell is None:
            return None
        return help_index_cell.exception

    @wraps(Cell.connect_from)
    def connect_from(self, *args, **kwargs):
        help_index_cell = self._help_index_cell(create=True)
        return help_index_cell.connect_from(*args, **kwargs)

    @wraps(Cell.checksum)
    def checksum(self):
        help_index_cell = self._help_index_cell()
        if help_index_cell is None:
            return None
        return help_index_cell.checksum

    @wraps(Cell.set_checksum)
    def set_checksum(self, *args, **kwargs):
        help_index_cell = self._help_index_cell()
        if help_index_cell is None:
            raise AttributeError
        help_index_cell.set_checksum(*args, **kwargs)

    @property
    def ctx(self):
        """Get the help context associated with this Seamless object
        The help context contains cells other than the index cell,
        and can contain subcontexts as well"""
        wrapped = self._get_wrapped()
        if wrapped is None:
            raise AttributeError
        return HelpContext(wrapped)

    def __delattr__(self, attr):
        if attr.startswith("_"):
            return super().__delattr__(attr)
        help_index_cell = self._help_index_cell()
        if help_index_cell is None:
            raise AttributeError(attr)
        return help_index_cell.__delattr__(attr)


class HelpContext(HelpWrapper):

    @property
    def _context_path(self):        
        return ("HELP",) + self._path + ("CTX",) + self._sub_path

    def _create_subcontext(self):
        ctx = self._get_ctx()
        if ctx is None:
            raise AttributeError
        path = self._context_path
        nodes = ctx._graph[0]
        for n in range(1, len(path)+1):
            p = path[:n]
            if p not in nodes:
                nodes[p] = {
                    "path": p,
                    "type": "context"
                }

    def _get_subcontext(self):
        ctx = self._get_ctx()
        if ctx is None:
            raise AttributeError
        path = self._help_path
        nodes = ctx._graph[0]
        if path not in nodes:
            raise AttributeError
        if nodes[path]["type"] != "context":
            raise TypeError
        return SubContext(ctx, path)        

    def __getitem__(self, attr):
        if not isinstance(attr, str):
            raise KeyError(attr)
        return getattr(self, attr)

    def __setitem__(self, attr, value):
        if not isinstance(attr, str):
            raise KeyError(attr)
        setattr(self, attr, value)

    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if hasattr(type(self), attr) or attr in self.__dict__ or attr == "path":
            return super().__getattribute__(attr)
        ctx = self._get_ctx()
        if ctx is None:
            raise AttributeError
        path = self._context_path + (attr,)
        result = ctx._get_from_path(path)
        sub_path2 = self._sub_path + (attr,)
        if isinstance(result, Cell):
            return result
        elif isinstance(result, SubContext):
            return HelpContext(self._get_wrapped(), sub_path2)
        else:
            raise TypeError(type(result))

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        self._create_subcontext()
        ctx = self._get_ctx()
        path = self._context_path + (attr,)
        assign(ctx, path, value, help_context=True)

    @property
    @wraps(SubContext.status)
    def status(self):
        subcontext = self._get_subcontext()
        return subcontext.status

    @wraps(SubContext.get_children)
    def get_children(self):
        subcontext = self._get_subcontext()
        return subcontext.get_children()

    @wraps(SubContext.children)
    def children(self):
        subcontext = self._get_subcontext()
        return subcontext.children

    def __delattr__(self, attr):
        if attr.startswith("_"):
            return super().__delattr__(attr)
        ctx = self._get_ctx()
        path = self._context_path + (attr,)
        ctx._destroy_path(path)

    def __dir__(self):
        d = [p for p in type(self).__dict__ if not p.startswith("_")]
        return sorted(d + self.get_children())

   
from .Context import SubContext
from .assign import get_new_cell, assign