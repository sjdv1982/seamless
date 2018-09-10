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
from ..midlevel import copy_context
from ..midlevel import TRANSLATION_PREFIX
from ..midlevel.library import register_library
from .Library import get_lib_paths

class ContextMixin:
    def __call__(self, *args, **kwargs):
        if self._constructor is None:
            raise TypeError("Context has no constructor")
        raise NotImplementedError
        self2 = self._copy()
        result = self._constructor(self2, *args, **kwargs)
        assert isinstance(result, Context)

    def _run_copier(self):
        if self._copier is None: return self #kludge
        raise NotImplementedError
        self2 = self._copy()
        if self._copier is None:
            return self2
        return self._copier(self2)

    def _copy(self):
        ### TODO
        ### - clean Context copy using _get_graph (makes SubContext independent)
        ### - eliminate _constructor;
        ### - implement _export and _default_export (from parent in case of SubContext)
        raise NotImplementedError

Graph = namedtuple("Graph", ("nodes", "connections", "subcontexts"))

class Context(ContextMixin):
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
        self._export = {} # dict with export indications (True, False and None values)
                          # This is used when the context is copied
                          # They apply for all children as well, until overridden
        self._default_export = True  #meaning of the None value in _export
        self._copier = None # Custom copier function (optional)
        self._constructor = None # Custom constructor function
                                 # (optional, mutually exclusive with copier)
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
        # TODO: add translate to the work queue, so that it will run automatically at some point
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
        self._register_library()
        self._needs_translation = False

    def _get_graph(self):
        nodes, connections, subcontexts = self._graph
        nodes, connections = deepcopy(nodes), deepcopy(connections)
        copy_context.fill_cell_values(self, nodes)
        return nodes, connections

    def _register_library(self):
        ctx_functor = lambda: getattr(self._ctx, TRANSLATION_PREFIX)
        if self._as_lib is not None:
            callback = partial(register_library, ctx_functor, self, self._as_lib)
            self._ctx._get_manager().on_equilibrate(callback)

class SubContext(Base, ContextMixin):
    def __init__(self, parent, path):
        super().__init__(parent, path)
        self._copier = None
        self._constructor = None

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
        nodes, connections = copy_context.copy_context(nodes, connections, path)
        copy_context.fill_cell_values(parent, nodes, path)
        return nodes, connections

    @property
    def from_lib(self):
        p = self._parent()._graph.subcontexts.get(self._path, {})
        return p.get("from_lib")
