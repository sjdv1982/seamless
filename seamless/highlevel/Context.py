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

class Context:
    path = ()
    _graph_ctx = None
    _depsgraph = None
    def __init__(self, dummy=False):
        self._dummy = dummy
        if not dummy:
            with macro_mode_on(self):
                self._ctx = context(toplevel=True)
        self._gen_context = None
        self._graph = Graph({},[],{"from_lib": None})
        self._children = {}
        self._needs_translation = True
        self._as_lib = None
        self._parent = weakref.ref(self)
        if not self._dummy:
            self._depsgraph = DepsGraph(self)

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
        return Proxy(self, path, "w", None)

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
        if isinstance(value, (Reactor, Transformer)):
            value._init(self, (attr,) )
            self.translate(force=True)
        else:
            assign(self, (attr,) , value)

    def __delattr__(self, attr):
        self._destroy_path((attr,))

    def mount(self, mountdir, persistent=None):
        assert not self._dummy
        with macro_mode_on():
            ctx = self._ctx
            ctx.mount(mountdir, persistent=persistent)
            mountmanager.add_context(ctx,(), False)
            mountmanager.paths[ctx].add(mountdir) #kludge

    def mount_graph(self, mountdir, persistent=None):
        assert not self._dummy
        with macro_mode_on(self):
            ctx = self._graph_ctx = context(toplevel=True)
        with macro_mode_on():
            ctx.mount(mountdir, persistent=persistent, mode="w")
            mountmanager.add_context(ctx,(), False)
            mountmanager.paths[ctx].add(mountdir) #kludge
        with macro_mode_on():
            ctx.topology = cell("json")
            ctx.values = cell("json")
            ctx.states = cell("json")

    def equilibrate(self):
        if self._dummy:
            return
        self.translate()
        self._ctx.equilibrate()

    def self(self):
        raise NotImplementedError

    def _translate(self):
        self._needs_translation = True

    def translate(self, force=False):
        if self._dummy:
            return
        assert self._as_lib is None or self._from_lib is None
        is_lib = (self.as_lib is not None)
        if not force and not self._needs_translation:
            return
        self._remount_graph()
        graph = list(self._graph[0].values()) + self._graph[1]
        #from pprint import pprint; pprint(graph)
        try:
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
                layer.clear_objects(self._gen_context)
                self._gen_context.self.destroy()
                self._gen_context._manager.flush()
                self._gen_context.full_destroy()
            self._gen_context = ctx
        except Exception as exc:
            if not ok:
                traceback.print_exc()
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
        self._needs_translation = False

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
            nodes, connections = self._graph.nodes, self._graph.connections
            topology, values, states, _, _ = extract(nodes, connections)
            self._graph_ctx.topology.set(topology)
            self._graph_ctx.values.set(values)
            self._graph_ctx.states.set(states)
            mountmanager.tick()

    def register_library(self):
        assert not self._dummy
        assert self._as_lib is not None #must be a library
        libitem = self._as_lib
        self.equilibrate()
        ctx = getattr(self._ctx, TRANSLATION_PREFIX)
        libname = self._as_lib.name
        partial_authority = register_library(ctx, self, libname)
        if partial_authority != libitem.partial_authority:
            libitem.needs_update = True
            libitem.partial_authority = partial_authority
        libitem.update()

    def set_constructor(self, *, constructor, post_constructor, args, direct_library_access):
        from .Library import set_constructor
        assert not self._dummy
        assert self._as_lib is not None #must be a library
        libname = self._as_lib.name
        set_constructor(libname, constructor, post_constructor, args, direct_library_access)

    def _destroy_path(self, path):
        for p in list(self._children.keys()):
            if p[:len(path)] == path:
                child = self._children.pop(p)
                if child["type"] == "context":
                    libname = child.get("from_lib")
                    if libname is not None:
                        libitem = get_libitem(libname)
                        libitem.copy_deps.remove((weakref.ref(self), path))
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
                           or con["target"][:len(path)] != path ]
        if len(connections) < l:
            self._translate()


    def status(self):
        assert not self._dummy
        return self._ctx.status()


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
        sub = self._parent()._children[self._path]
        return sub.get("from_lib")

    def touch(self):
        """Re-evaluates all constructor dependencies
        This is meant for a library contexts where direct library update has been
        disabled by the constructor, or otherwise some bug has happened"""
        if self._as_lib is None:
            return
        ctx._as_lib.library.touch(self)

class LibraryContextInstance:
    def __init__(self, libname, *args, **kwargs):
        self.libname = libname
        self.args = args
        self.kwargs = kwargs

from .Reactor import Reactor
from .Transformer import Transformer
