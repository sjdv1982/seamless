from copy import deepcopy
from .unbound_context import UnboundContext
import weakref


class HighLevelContext(UnboundContext):
    """Low-level sub-context that is a direct translation of a high-level context graph.
    Accessing this object via the parent using attribute access will not return it.
    Instead, a synthesized high-level context (SynthContext) around the graph
    will be returned"""

    def __init__(self, graph):
        from ..midlevel.StaticContext import StaticContext

        if isinstance(graph, StaticContext):
            graph = graph.get_graph()
        else:
            graph = deepcopy(graph)
        for node in graph["nodes"]:
            node.pop("mount", None)
            node.pop("share", None)
            node["path"] = tuple(node["path"])
        for con in graph["connections"]:
            if con["type"] == "connection":
                con["source"] = tuple(con["source"])
                con["target"] = tuple(con["target"])
            elif con["type"] == "link":
                con["first"] = tuple(con["first"])
                con["second"] = tuple(con["second"])
        self._graph = graph
        super().__init__()

    def _translate(self, root_highlevel_ctx):
        from .macro_mode import curr_macro
        from ..midlevel.translate import translate
        from ..highlevel.assign import _assign_context
        from ..highlevel.Context import Context

        if root_highlevel_ctx is None:
            raise TypeError(
                "HighLevelContext cannot be part of a dissociated low-level context; there must be high-level root"
            )
        if not isinstance(root_highlevel_ctx, Context):
            raise TypeError(type(root_highlevel_ctx))
        graph = self._graph
        translate(graph, self, root_highlevel_ctx.environment)
        path = curr_macro().path + ("ctx",) + self.path
        _assign_context(
            root_highlevel_ctx,
            graph["nodes"],
            graph["connections"],
            path,
            runtime=True,
            fast=True,
        )
        self._synth_highlevel_context = weakref.ref(root_highlevel_ctx)

    def __getitem__(self, attr):
        if not isinstance(attr, str):
            raise KeyError(attr)
        return getattr(self, attr)
