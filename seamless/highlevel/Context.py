import traceback
from copy import deepcopy
from collections import namedtuple
import weakref
from functools import partial

from .Base import Base
from ..core import macro_mode
from ..core.macro_mode import macro_mode_on, macro_mode_off, get_macro_mode
from ..core.context import context, Context as CoreContext
from ..core.cell import cell
from ..core.mount import mountmanager #for now, just a single global mountmanager
from ..midlevel.translate import translate
from .assign import assign
from .proxy import Proxy
from ..midlevel import copying
from ..midlevel.library import register_library
from .Library import get_lib_paths, get_libitem
from .depsgraph import DepsGraph

Graph = namedtuple("Graph", ("nodes", "connections", "params"))

shareserver = None


class Context:
    path = ()
    _mount = None
    _gen_context = None
    _graph_ctx = None
    _depsgraph = None
    _translating = False
    _as_lib = None
    _auto_register_library = False
    _shares = None
    _translate_count = 0  

    @classmethod
    def from_graph(cls, graph, cache_manager):
        self = cls()
        if cache_manager is not None:
            #self._ctx0._get_manager()._set_cache(cache_manager)
            self._ctx0._manager = cache_manager
        graph = deepcopy(graph)
        nodes = {}        
        for node in graph["nodes"]:
            p = tuple(node["path"])
            node["path"] = p
            nodes[p] = node
            nodetype = node["type"]
            nodecls = nodeclasses[nodetype]
            child = nodecls(parent=self,path=p)
        connections = graph["connections"]
        for con in connections:
            con["source"] = tuple(con["source"])
            con["target"] = tuple(con["target"])
        self._graph = Graph(nodes, connections, graph["params"])
        return self

    def __init__(self, dummy=False):
        self._dummy = dummy
        if not dummy:            
            with macro_mode_on(self):
                self._ctx0 = context(toplevel=True)
                ctx = self._ctx0._root_
                self._gen_context = ctx
                self._ctx0._bind(ctx)
            macro_mode._toplevel_registered.add(ctx)
        self._graph = Graph({},[],{"from_lib": None})
        self._children = {}
        self._needs_translation = True
        self._parent = weakref.ref(self)
        if not self._dummy:
            self._depsgraph = DepsGraph(self)
        self._traitlets = {}

    def __call__(self, *args, **kwargs):
        assert self._as_lib is not None #only libraries have constructors
        libname = self._as_lib.name
        return LibraryContextInstance(libname, *args, **kwargs)

    def _get_path(self, path):
        child = self._children.get(path)
        if child is not None:
            return child
        node = self._graph[0].get(path)
        if node is not None:
            assert node["type"] == "context", (path, node["type"]) #if not context, should be in children!
            return SubContext(self, path)
        return Proxy(self, path, "w")

    def _get_subcontext(self, path):
        child = self._children[path]

    @property
    def from_lib(self):
        return self._graph.params.get("from_lib")

    @from_lib.setter
    def from_lib(self, value):
        self._graph.params["from_lib"] = value

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        path = (attr,)
        return self._get_path(path)

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        attr2 = (attr,)
        if isinstance(value, Reactor):
            value._init(self, (attr,) )
            self._translate()
        elif isinstance(value, Transformer):
            if value._parent is None:
                self._graph[0][attr2] = value
                self._children[attr2] = value
                value._init(self, attr2 )
                self._translate()
            else:
                assign(self, attr2, value)
            """
        elif attr2 in self._children:
            child = self._children[attr2]
            if isinstance(child, Cell):
                child.set(value)
            """
        else:
            assign(self, attr2, value)

    def __delattr__(self, attr):
        self._destroy_path((attr,))

    def _add_traitlet(self, path, subpath, fresh):
        from .SeamlessTraitlet import SeamlessTraitlet
        traitlet = self._traitlets.get((path, subpath))
        traitlet = SeamlessTraitlet(value=None)
        traitlet.parent = weakref.ref(self)
        traitlet.path = path
        traitlet.subpath = subpath
        traitlet._connect()
        self._traitlets[(path, subpath)] = traitlet
        return traitlet

    def auto_register(self, auto_register=True):
        """See the doc of Library.py"""
        if not self._as_lib:
            raise TypeError("Context must be a library")
        self._auto_register_library = True
        self._do_translate(force=True)

    def mount(self, path=None, mode="rw", authority="cell", persistent=None):
        assert not self._dummy
        if self._parent() is not self:
            raise NotImplementedError
        if path is None:
            self._mount = None
            self._ctx0.mount(None)
            return
        self._mount = {
            "path": path,
            "mode": mode,
            "authority": authority,
            "persistent": persistent
        }
        with macro_mode_on():
            ctx = self._ctx0
            ctx.mount(**self._mount)
            mountmanager.add_context(ctx,(), False)
            mountmanager.paths[ctx._root()].add(path) #kludge
        self._translate()

    def mount_graph(self, mountdir, persistent=None):
        assert not self._dummy
        with macro_mode_on(self):
            if self._graph_ctx is not None:
                self._graph_ctx.destroy()
            ctx = self._graph_ctx = context(toplevel=True)
        with macro_mode_on():
            ctx.mount(mountdir, persistent=persistent, mode="w")
            mountmanager.add_context(ctx,(), False)
            mountmanager.paths[ctx].add(mountdir) #kludge
        with macro_mode_on():
            raise NotImplementedError ### cache branch
            """
            ctx.topology = cell("json")
            ctx.values = cell("json") #TODO: change to mixed
            ctx.cached_values = cell("json") #TODO: change to mixed
            ctx.states = cell("json") #TODO: change to mixed
            ctx.cached_states = cell("json") #TODO: change to mixed
            """
        self._translate()

    def equilibrate(self, timeout=None):
        if self._dummy:
            return
        self.translate()
        return self._ctx0.equilibrate(timeout)

    def self(self):
        raise NotImplementedError

    def _translate(self):
        self._needs_translation = True

    def translate(self, force=False):
        return self._do_translate(force=force, explicit=True)

    def get_graph(self, copy=True):        
        try:
            self._translating = True
            manager = self._ctx0._bound._get_manager()            
            copying.fill_checksums(manager, self._graph.nodes)            
        finally:
            self._translating = False
        # put nodes in alphabetical order; shouldn't matter much except for reproducibility of Seamless bugs
        nodes, connections, params = self._graph
        nodes = [v for k,v in sorted(nodes.items(), key=lambda kv: kv[0])]
        if copy:
            connections = deepcopy(connections)
            nodes = deepcopy(nodes)
            params = deepcopy(params)
        graph = {"nodes": nodes, "connections": connections, "params": params}
        return graph

    def _do_translate(self, force=False, explicit=False):        
        if self._dummy:
            return
        assert self._as_lib is None or self._from_lib is None
        is_lib = (self._as_lib is not None)
        if not force and not self._needs_translation:
            return
        if self._translating:
            raise Exception("Nested invocation of ctx.translate")
        ### TODO: check that current_macro is not part of self._ctx0
        ###from ..core.macro_mode import get_macro_mode
        ###assert not get_macro_mode()
        self._translate_count += 1
        graph = self.get_graph(copy=False)
        try:            
            self._translating = True
            ctx = None
            ok = False
            manager = self._ctx0._get_manager()               
            with macro_mode_off():
                ctx = CoreContext(toplevel=True)
            macro_mode._toplevel_registered.add(ctx)
            ctx._manager = manager
            ctx._macro = self
            assert not len(ctx.path)
            old_gen_context = self._gen_context
            if old_gen_context is not None:
                old_gen_context.destroy()
            with macro_mode_on(self):
                ub_ctx = context(toplevel=True, manager=manager) 
                self._unbound_context = ub_ctx                
                lib_paths = get_lib_paths(self)
                translate(graph, ub_ctx, lib_paths, is_lib)
                ok = True
                ub_ctx._bind(ctx)                
                assert not len(ctx.path)
                self._gen_context = ctx
                ub_ctx._root_.destroy()               
                for traitlet in self._traitlets.values():
                    traitlet._connect()
                self._connect_share()
        finally:
            self._translating = False
            self._unbound_context = None

        """
        # TODO: cell update hooks, for library
        if self._auto_register_library:
            ctx._get_manager().cell_update_hook(self._library_update_hook)
        """
        
        self._needs_translation = False

        if ok:
            for path, child in self._children.items():
                if isinstance(child, (Cell, Transformer)):
                    child._set_observers()
                elif isinstance(child, (InputPin, OutputPin)):
                    continue
                else:
                    raise NotImplementedError(type(child)) ### cache branch

        if explicit and self._auto_register_library:
            #the timeout is just a precaution
            self.register_library(timeout=5)

    def _connect_share(self):
        if self._shares is None:
            return
        from ..core import StructuredCell, Cell as core_cell
        sharedict = {}        
        for path in self._shares:
            key = "/".join(path) #TODO: split in subpaths by inspecting and traversing ctx._children (recursively for subcontext children)
            hcell = self._children[path]
            if not isinstance(hcell, Cell):
                raise NotImplementedError(type(hcell))
            cell = hcell._get_cell()
            if isinstance(cell, StructuredCell):
                pass #TODO: see above
            elif isinstance(cell, core_cell):
                pass #TODO: see above
            else:
                raise TypeError(cell)
            sharedict[key] = cell, hcell.mimetype

        if shareserver is not None:
            shareserver.share(self._share_namespace, sharedict)
        for key, value in sharedict.items():
            cell = value[0]
            sharefunc = partial(shareserver.send_update, self._share_namespace, key)
            cell._set_share_callback(sharefunc)
            sharefunc()



    def register_library(self, timeout=None):
        assert not self._dummy
        assert self._as_lib is not None #must be a library
        libitem = self._as_lib
        result = self.equilibrate(timeout)
        ctx = self._gen_context
        libname = self._as_lib.name
        register_library(ctx, self, libname)
        libitem.needs_update = True
        libitem.update()

    def _library_update_hook(self, cell, value):
        if self._translating:
            return
        #the timeout is just a precaution;
        # since the _flushing hack on core/mainloop.py,
        # this is not longer blocking
        self.register_library(timeout=5) #TODO: fix after New Way

    def set_constructor(self, *, constructor, post_constructor, args, direct_library_access):
        from .Library import set_constructor
        assert not self._dummy
        assert self._as_lib is not None #must be a library
        libname = self._as_lib.name
        set_constructor(libname, constructor, post_constructor, args, direct_library_access)

    def _destroy_path(self, path):
        nodes = self._graph.nodes
        for p in list(nodes.keys()):
            if p[:len(path)] == path:
                node = nodes[p]
                child = self._children.get(p)
                if node["type"] == "context":
                    assert child is None
                    libname = node.get("from_lib")
                    if libname is not None:
                        libitem = get_libitem(libname)
                        libitem.copy_deps.remove((weakref.ref(self), path))
                nodes.pop(p)
                self._children.pop(p, None)
                if self._shares is not None:
                    self._shares.pop(p, None)
                self._translate()

        nodes = self._graph.nodes
        l = len(nodes)
        newnodes = {k:v for k,v in nodes.items() \
                    if k[:len(path)] != path }
        if len(newnodes) < l:
            nodes.clear()
            nodes.update(newnodes)
            self._translate()

        connections = self._graph.connections
        l = len(connections)
        connections[:] = [con for con in connections \
                           if con["source"][:len(path)] != path \
                           and con["target"][:len(path)] != path ]
        if len(connections) < l:
            self._translate()


    @property
    def status(self):
        """The computation status of the context
        Returns a dictionary containing the status of all children that are not OK.
        If all children are OK, returns OK
        """
        from ..core.context import StatusReport
        assert not self._dummy
        result = StatusReport()
        for childname0, child in self._children.items():
            if len(childname0) > 1:
                continue
            childname = childname0[0]
            s = child.status
            if s != "OK" and s != "FINISHED":
                result[childname] = s
        if len(result):
            return result
        else:
            return "OK"

    def _root(self):
        # Needed so that Context can pretend to be a low-level macro
        return self._ctx0._bound

    def _context(self):
        # Needed so that Context can pretend to be a low-level macro
        return self._ctx0._bound
        
    def _remove_connections(self, path):
        # Removes all connections starting with path
        lp = len(path)
        def keep_con(con):
            ctarget = con["target"]
            return ctarget[:lp] != path
        self._graph[1][:] = filter(keep_con, self._graph[1])

    def _share(self, cell):
        key = ".".join(cell._path)
        if self._shares is None:
            global shareserver
            from .. import shareserver
            shareserver.start()
            self._share_namespace = shareserver.new_namespace("ctx")
            self._shares = set()
        self._shares.add(cell._path)
        self._translate()


    def __dir__(self):
        d = [p for p in type(self).__dict__ if not p.startswith("_")]
        subs = [p[0] for p in self._children]
        return sorted(d + list(set(subs)))


class SubContext(Base):
    def __init__(self, parent, path):
        super().__init__(parent, path)

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        parent = self._parent()
        path = self._path + (attr,)
        return parent._get_path(path)

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        parent = self._parent()
        path = self._path + (attr,)
        assign(parent, path, value)

    def __delattr__(self, attr):
        raise NotImplementedError

    def mount(self, mountdir):
        raise NotImplementedError

    def _get_graph(self):
        parent = self._parent()
        nodes, connections = parent._graph
        path = self._path
        nodes, connections = copying.copy_context(nodes, connections, path)
        #TODO:
        copying.fill_cell_values(parent, nodes, path)
        return nodes, connections

    @property
    def from_lib(self):
        sub = self._parent()._graph.nodes[self._path]
        return sub.get("from_lib")

    def touch(self):
        """Re-evaluates all constructor dependencies
        This is meant for a library contexts where direct library update has been
        disabled by the constructor, or otherwise some bug has happened"""
        if self._as_lib is None:
            return
        self._as_lib.library.touch(self)

    def __dir__(self):
        d = [p for p in type(self).__dict__ if not p.startswith("_")]
        l = len(self._path)
        subs = [p[l] for p in self._parent()._children if len(p) > l and p[:l] == self._path]
        return sorted(d + list(set(subs)))

class LibraryContextInstance:
    def __init__(self, libname, *args, **kwargs):
        self.libname = libname
        self.args = args
        self.kwargs = kwargs

from .Reactor import Reactor
from .Transformer import Transformer
from .Cell import Cell
from .pin import InputPin, OutputPin

nodeclasses = {
    "cell": Cell,
    "transformer": Transformer,
    "reactor": Reactor,
}