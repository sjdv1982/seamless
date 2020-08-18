from .unbound_context import UnboundContext

class HighLevelContext(UnboundContext):
    """Low-level sub-context that is a direct translation of a high-level context graph.
    Accessing this object via the parent using attribute access will not return it.
    Instead, a synthesized high-level context (SynthContext) around the graph
    will be returned"""
    def __init__(self, graph):
        from ..midlevel.StaticContext import StaticContext
        if isinstance(graph, StaticContext):
            graph = graph.get_graph()
        for node in graph["nodes"]:
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

    def _translate(self, highlevel_ctx):
        from .macro_mode import curr_macro
        from ..midlevel.translate import translate
        from ..highlevel.assign import _assign_context
        from ..highlevel.Context import Context
        if highlevel_ctx is None:
            raise TypeError("HighLevelContext cannot be part of a dissociated low-level context; there must be high-level root")
        if not isinstance(highlevel_ctx, Context):
            raise TypeError(type(highlevel_ctx))
        graph = self._graph
        translate(graph, self)
        path = curr_macro().path + ("ctx",) + self.path
        _assign_context(
            highlevel_ctx,
            graph["nodes"],
            graph["connections"],
            path,
            runtime=True
        )
        self._synth_highlevel_context = highlevel_ctx