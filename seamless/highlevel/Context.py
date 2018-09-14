import traceback
from copy import deepcopy
from collections import namedtuple
import weakref
from functools import partial

from .Base import Base
from ..core.macro_mode import macro_mode_on, get_macro_mode
from ..core.context import context, Context as CoreContext
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

Graph = namedtuple("Graph", ("nodes", "connections", "subcontexts"))

class Context:
    path = ()
    def __init__(self):
        with macro_mode_on(self):
            self._ctx = context(toplevel=True)
        self._gen_context = None
        self._graph = Graph({},[],{})
        self._graph.subcontexts[None] = {}
        self._children = {}
        self._context = self._ctx
        self._needs_translation = False
        self._as_lib = None
        self._parent = weakref.ref(self)

    def _get_path(self, path):
        child = self._children.get(path)
        if child is not None:
            return child
        node = self._graph[0].get(path)
        if node is not None:
            assert node["type"] == "context", (path, node["type"]) #should be in children!
            return SubContext(self, path)
        return Proxy(self, path, "w", None)

    @property
    def from_lib(self):
        return self._graph.subcontexts[None].get("from_lib")

    @from_lib.setter
    def from_lib(self, value):
        self._graph.subcontexts[None]["from_lib"] = value

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        path = (attr,)
        return self._get_path(path)

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        assign(self, (attr,) , value)

    def __delattr__(self, attr):
        assert (attr,) in self._children
        child = self._children.pop((attr,))
        child._destroy()
        self._translate()

    def mount(self, mountdir):
        with macro_mode_on():
            self._ctx.mount(mountdir, persistent=None)
            mountmanager.paths.add(mountdir) #kludge
            mountmanager.contexts.add(self._ctx) #kludge

    def equilibrate(self):
        self.translate()
        self._ctx.equilibrate()

    def self(self):
        raise NotImplementedError

    def _translate(self):
        self._needs_translation = True

    def translate(self, force=False):
        assert self._as_lib is None or self._from_lib is None
        is_lib = (self.as_lib is not None)
        if not force and not self._needs_translation:
            return
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
        nodes, connections, subcontexts = self._graph
        nodes, connections = deepcopy(nodes), deepcopy(connections)
        copying.fill_cell_values(self, nodes)
        return nodes, connections

    def register_library(self):
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

    def _del_subcontext(self, path):
        subcontexts = self._graph.subcontexts
        for p in list(subcontexts.keys()):
            if p is None:
                continue
            if p[:len(path)] == path:
                sc = subcontexts.pop(p)
                libname = sc.get("from_lib")
                if libname is not None:
                    libitem = get_libitem(libname)
                    libitem.copy_deps.remove((weakref.ref(self), path))

    def status(self):
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
        copying.fill_cell_values(parent, nodes, path)
        return nodes, connections

    @property
    def from_lib(self):
        p = self._parent()._graph.subcontexts.get(self._path, {})
        return p.get("from_lib")
