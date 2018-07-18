import traceback

from ..core.macro_mode import macro_mode_on, get_macro_mode
from ..core.context import context, Context as CoreContext
from ..core.mount import mountmanager #for now, just a single global mountmanager
from ..core.cache import cache
from ..core import layer
from ..midlevel.translate import translate
from .assign import assign
from .proxy import Proxy

class Context:
    path = ()
    def __init__(self):
        with macro_mode_on(self):
            self._ctx = context(toplevel=True)
        self._gen_context = None
        self._graph = {}, []
        self._children = {}
        self._context = self._ctx
        self._needs_translation = False

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        child = self._children.get((attr,))
        if child is not None:
            return child
        return Proxy(self, (attr,), "w", None)

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
                    ctx = context(context=self._ctx, name="translated")
                    translate(graph, ctx)
                    self._ctx._add_child("translated", ctx)
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
                            self._ctx._add_child("translated", self._gen_context)
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
