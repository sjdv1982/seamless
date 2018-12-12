import traceback
from copy import deepcopy
from collections import namedtuple
import weakref
from functools import partial

from .Base import Base
from ..core.macro_mode import macro_mode_on, get_macro_mode
from ..core.context import context, Context as CoreContext
from ..core.cell import cell
from ..core.mount import mountmanager #for now, just a single global mountmanager
from ..core.cache import cache
from ..core import layer
from ..midlevel.translate import translate
from .assign import assign
from .proxy import Proxy
from ..midlevel import copying
from ..midlevel import TRANSLATION_PREFIX
from ..midlevel.library import register_library
from .Library import get_lib_paths, get_libitem
from .depsgraph import DepsGraph

Graph = namedtuple("Graph", ("nodes", "connections", "params"))

shareserver = None
SeamlessTraitlet = None
try:
    import traitlets
    class SeamlessTraitlet(traitlets.HasTraits):
        value = traitlets.Instance(object)
        _updating = False
        path = None
        subpath = None
        parent = None
        def _connect(self):
            from ..core import StructuredCell, Cell as core_cell
            hcell = self.parent()._children[self.path]
            if not isinstance(hcell, Cell):
                raise NotImplementedError(type(hcell))
            cell = hcell._get_cell()
            ccell = None
            if isinstance(cell, StructuredCell):
                subpath = self.subpath
                if subpath is not None:
                    subpath = ()
                if subpath in cell.inchannels:
                    raise NotImplementedError
                    ccell = cell.inchannels[subpath]
                elif subpath in cell.outchannels:
                    if subpath == (): ###
                        ccell = cell
                    raise NotImplementedError
                    #ccell = cell.outchannels[subpath]
                else:
                    ccell = cell
            elif isinstance(cell, core_cell):
                assert subpath is None
                raise NotImplementedError
                ccell = cell
            else:
                raise TypeError(cell)
            if ccell is not None:
                print("traitlet %s:%s, observing" % (self.path, self.subpath))
                ccell._set_observer(self.receive_update)

        def receive_update(self, value):
            #print("Traitlet RECEIVE UPDATE", self.path, self.subpath, value)
            self._updating = True
            self.value = value
            self._updating = False

        @traitlets.observe('value')
        def _value_changed(self, change):
            if self.parent is None:
                return
            #print("Traitlet DETECT VALUE CHANGE", self.path, self.subpath, change, self._updating)
            if self._updating:
                return
            value = change["new"]
            hcell = self.parent()._children[self.path]
            handle = hcell
            if self.subpath is not None:
                for p in self.subpath:
                    handle = getattr(handle, p)
            handle.set(value)


except ImportError:
    pass

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
    def __init__(self, dummy=False):
        self._dummy = dummy
        if not dummy:
            with macro_mode_on(self):
                self._ctx = context(toplevel=True)
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
        elif isinstance(value, Transformer) and value._parent is None:
            self._graph[0][attr2] = value
            self._children[attr2] = value
            value._init(self, attr2 )
            self._translate()
        elif attr2 in self._children:
            self._children[attr2].set(value)
        else:
            assign(self, attr2, value)

    def __delattr__(self, attr):
        self._destroy_path((attr,))

    def _add_traitlet(self, path, subpath):
        traitlet = self._traitlets.get((path, subpath))
        if traitlet is not None:
            return traitlet
        if SeamlessTraitlet is None:
            raise ImportError("cannot find traitlets module")
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

    def mount(self, path=None, mode="rw", authority="cell", persistent=False):
        assert not self._dummy
        if self._parent() is not self:
            raise NotImplementedError
        if path is None:
            self._mount = None
            self._ctx.mount(None)
            return
        self._mount = {
            "path": path,
            "mode": mode,
            "authority": authority,
            "persistent": persistent
        }
        with macro_mode_on():
            ctx = self._ctx
            ctx.mount(**self._mount)
            mountmanager.add_context(ctx,(), False)
            mountmanager.paths[ctx].add(path) #kludge
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
            ctx.topology = cell("json")
            ctx.values = cell("json") #TODO: change to mixed
            ctx.cached_values = cell("json") #TODO: change to mixed
            ctx.states = cell("json") #TODO: change to mixed
            ctx.cached_states = cell("json") #TODO: change to mixed
        self._translate()

    def equilibrate(self, timeout=None):
        if self._dummy:
            return
        self.translate()
        return self._ctx.equilibrate(timeout)

    def self(self):
        raise NotImplementedError

    def _translate(self):
        self._needs_translation = True

    def translate(self, force=False):
        return self._do_translate(force=force, explicit=True)

    def _do_translate(self, force=False, explicit=False):
        if self._dummy:
            return
        assert self._as_lib is None or self._from_lib is None
        is_lib = (self._as_lib is not None)
        if not force and not self._needs_translation:
            return
        if self._translating:
            raise Exception("Nested invocation of ctx.translate")
        from ..core.macro_mode import get_macro_mode
        assert not get_macro_mode()
        try:
            self._translating = True
            if self._ctx is not None and hasattr(self._ctx, TRANSLATION_PREFIX):
                copying.fill_cell_values(self, self._graph.nodes)
            self._remount_graph()
        finally:
            self._translating = False
        # nodes must be in alphabetical order; this matters for linked cells that each have their own value!
        graph = [v for k,v in sorted(self._graph.nodes.items(), key=lambda kv: kv[0])]
        graph += self._graph.connections
        #from pprint import pprint; pprint(graph)
        root = self._ctx._get_manager()._root()
        old_cell_update_hook = root._cell_update_hook
        try:
            root._cell_update_hook = None
            self._translating = True
            ctx = None
            ok = False
            if self._gen_context is not None:
                self._gen_context._manager.deactivate()
                old_layers = layer.get_layers(self)
                layer.destroy_layer(self)
            layer.create_layer(self)
            with mountmanager.reorganize(self._gen_context):
                with macro_mode_on():
                    ctx = context(context=self._ctx, name=TRANSLATION_PREFIX)
                    lib_paths = get_lib_paths(self)
                    assert mountmanager.reorganizing
                    translate(graph, ctx, lib_paths, is_lib)
                    self._ctx._add_child(TRANSLATION_PREFIX, ctx)
                    ctx._get_manager().activate(only_macros=True)
                    ok = True
                    layer.fill_objects(ctx, self)
                    if self._gen_context is not None:
                        #hits = cache(ctx, self._gen_context) ### TODO: re-enable caching
                        hits = []

            with macro_mode_on():
                def seal(c):
                    c._seal = self._ctx
                    for child in c._children.values():
                        if isinstance(child, CoreContext):
                            seal(child)
                seal(ctx)
                layer.check_async_macro_contexts(ctx, self)
                ctx._get_manager().activate(only_macros=False)

            if self._gen_context is not None:
                with mountmanager.reorganize(None):
                    layer.clear_objects(self._gen_context)
                    self._gen_context.self.destroy()
                    self._gen_context._manager.flush()
                    self._gen_context.full_destroy()
            self._gen_context = ctx
        except Exception as exc:
            if not ok:
                ###traceback.print_exc()  #not if we raise...
                try:
                    if ctx is not None:
                        ctx.self.destroy()
                        ctx.full_destroy()
                    if self._gen_context is not None:
                        with macro_mode_on():
                            self._gen_context._remount()
                            self._ctx._add_child(TRANSLATION_PREFIX, self._gen_context)
                        layer.restore_layers(self, old_layers)
                        self._gen_context._manager.activate(only_macros=False)
                except Exception as exc2:
                    traceback.print_exc()
                    self.secondary_exception = traceback.format_exc()
            else:
                # new context was constructed successfully
                # but something went wrong in cleaning up the old context
                # pretend that nothing happened...
                # but store the exception as secondary exception, just in case
                print("highlevel context CLEANUP error"); traceback.print_exc()
                self._gen_context = ctx
            raise
        finally:
            root._cell_update_hook = old_cell_update_hook
            self._translating = False
        if self._auto_register_library:
            ctx._get_manager().cell_update_hook(self._library_update_hook)

        try:
            self._translating = True
            copying.fill_cell_values(self, self._graph.nodes) #do it again, because we can get the real values from the low-level cells now
            self._remount_graph() #do it again, because TEMP values may have been popped, and we have now real values instead
            for traitlet in self._traitlets.values():
                traitlet._connect()
            self._connect_share()
        finally:
            self._translating = False
        self._needs_translation = False
        if explicit and self._auto_register_library:
            #the timeout is just a precaution
            self.register_library(timeout=5)

    def _connect_share(self):
        from ..core import StructuredCell, Cell as core_cell
        sharedict = {}
        if self._shares is not None:
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
                sharedict[key] = cell

        if shareserver is not None:
            shareserver.share(self._share_namespace, sharedict)
        for key, cell in sharedict.items():
            sharefunc = partial(shareserver.send_update, self._share_namespace, key)
            cell._set_share_callback(sharefunc)
            sharefunc()


    def _get_graph(self):
        nodes, connections, params = self._graph
        nodes, connections = deepcopy(nodes), deepcopy(connections)
        copying.fill_cell_values(self, nodes)
        return nodes, connections

    def _remount_graph(self):
        if self._dummy:
            return
        from ..midlevel.serialize import extract
        if self._graph_ctx is not None:
            ctx = self._graph_ctx
            nodes, connections = self._graph.nodes, self._graph.connections
            topology, values, states, cached_values, cached_states = extract(nodes, connections)
            ctx.topology.set(topology)
            ctx.values.set(values)
            ctx.cached_values.set(cached_values)
            ctx.states.set(states)
            ctx.cached_states.set(cached_states)
            mountmanager.tick()

    def register_library(self, timeout=None):
        assert not self._dummy
        assert self._as_lib is not None #must be a library
        libitem = self._as_lib
        root = self._ctx._get_manager()._root()
        old_cell_update_hook = root._cell_update_hook
        try:
            root._cell_update_hook = None
            result = self.equilibrate(timeout)
            ctx = getattr(self._ctx, TRANSLATION_PREFIX)
            libname = self._as_lib.name
            partial_authority = register_library(ctx, self, libname)
            if partial_authority != libitem.partial_authority:
                libitem.needs_update = True
                libitem.partial_authority = partial_authority
            libitem.update()
        finally:
            root._cell_update_hook = old_cell_update_hook

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


    def status(self):
        assert not self._dummy
        return self._ctx.status()

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
