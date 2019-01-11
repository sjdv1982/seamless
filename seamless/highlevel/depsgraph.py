import weakref
from copy import deepcopy

from . import parse_function_code

class DepsGraph:
    def __init__(self, ctx):
        self._id = 0
        self.ctx = weakref.ref(ctx)
        self.inputs_fwd = {} #path-to-list-of-dependencies that depend on this path
        self.results = {} #path-to-dependency that represents this path
        self.inputs_bwd = {} #dep_id-to-input-paths on which the dependency depends

    def construct_library(self, libname, result_path, args, kwargs):
        from .Library import get_libitem
        dep = {"libname": libname, "result_path": result_path}
        libitem = get_libitem(libname)
        constructor = libitem.constructor
        assert constructor is not None, libname
        parsed_args = constructor.parse_args(args, kwargs)
        dep["parsed_args"] = parsed_args
        dep["direct_library_access"] = constructor.direct_library_access
        input_paths = [v["value"] for k,v in parsed_args.items() if v["is_path"]]
        inputs_bwd = []
        for path in input_paths:
            if path not in self.inputs:
                self.inputs_fwd[path] = []
            self.inputs_fwd[path].append(dep)
            inputs_bwd.append(path)
        self.remove_path(result_path)
        self.results[result_path] = dep
        self.inputs_bwd[id(dep)] = inputs_bwd
        return dep

    def evaluate_dep(self, dep):
        from .Context import Context
        from .assign import _assign_context
        from .Library import get_libitem
        ctx = self.ctx()
        libitem = get_libitem(dep["libname"])
        result_path = dep["result_path"]
        args = {}
        for argname, parsed_arg in dep["parsed_args"].items():
            value = parsed_arg["value"]
            if parsed_arg["is_path"]:
                path = value
                assert path in ctx._children, (argname, path)
                cell = ctx._children[path]
                if parsed_arg["auth"]:
                    assert cell.authoritative, (argname, cell)
                if parsed_arg["as_cell"]:
                    value = cell
                else:
                    value = cell.value
            args[argname] = value

        constructor = libitem.constructor.constructor
        libctx = getattr(libitem.library, libitem.childname)
        from_lib = libctx._as_lib
        if not dep["direct_library_access"]:
            from_lib = None
        nodes, connections, _ = libctx._graph
        new_nodes, new_connections = \
          deepcopy(nodes), deepcopy(connections)
        if constructor is not None:
            new_ctx0 = Context(dummy=True)
            new_ctx0._graph.nodes.update(new_nodes)
            new_ctx0._graph.connections[:] = new_connections
            for path, child in libctx._children.items():
                type(child)(new_ctx0, path) #inserts itself in new_ctx0._children
            new_ctx = constructor(new_ctx0, **args)
            assert isinstance(new_ctx, Context)
            new_nodes, new_connections = new_ctx._graph.nodes, new_ctx._graph.connections
        _assign_context(ctx, new_nodes, new_connections, result_path, from_lib)
        post_constructor = libitem.constructor.post_constructor
        if post_constructor is not None:
            new_ctx2 = ctx._get_subcontext(result_path)
            post_constructor(new_ctx2, **args)
        self.update_path(result_path)

    def update_path(self, path):
        for n in range(len(path)):
            p = path[:n]
            for dep in self.inputs_fwd.get(p, []):
                self.evaluate_dep(dep)

    def remove_path(self, path):
        fwds = self.inputs_fwd.pop(path, []) #this path => other paths
        ctx = self.ctx()
        for path in fwds:
            ctx._destroy_path(path)
        dep = self.results.pop(path, None) #dep => this path
        if dep is None:
            return
        for path in self.inputs_bwd[id(dep)]: #other paths => dep
            self.inputs_fwd[path].remove()
