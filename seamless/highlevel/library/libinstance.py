import traceback
import weakref, json
from copy import deepcopy

highlevel_names = ("Context", "Cell", "Transformer", "Macro", "Module")

class LibInstance:
    
    def __init__(self, parent, *, path=None, libpath=None, arguments=None):
        self._parent = weakref.ref(parent)
        self._path = path
        self._temp_libpath = libpath
        self._temp_arguments = arguments
        self._overlay_context = None

    def _bind(self, ctx, path):
        assert ctx is self._parent() # must have same top-level Context as the library
        assert self._path is None, self._path
        assert self._temp_libpath is not None
        assert self._temp_arguments is not None
        self._path = path
        node = {
            "path": path,
            "type": "libinstance",
            "libpath": self._temp_libpath,
            "arguments": self._temp_arguments,
        }
        json.dumps(node)
        ctx._graph.nodes[path] = node
        self._temp_libpath = None
        self._temp_arguments = None

    def _get_node(self):
        parent = self._parent()
        return parent._graph.nodes[self._path]

    def _run(self):
        assert self._path is not None
        hnode = self._get_node()
        libpath = hnode["libpath"]
        arguments = hnode["arguments"]
        parent = self._parent()
        lib = parent._get_lib(tuple(libpath))
        graph = lib["graph"]
        constructor = lib["constructor"]
        params = lib["params"]

        overlay_context = Context(manager=parent._manager)
        self._overlay_context = overlay_context
        namespace = {
            "ctx": overlay_context
        }
        connection_wrapper = ConnectionWrapper(self._path + ("ctx",))
        overlay_nodes = {}
        for argname, argvalue in arguments.items():
            par = params[argname]
            if par["type"] == "value":
                value = argvalue
            elif par["type"] == "cell":
                if isinstance(argvalue, list):
                    argvalue = tuple(argvalue)
                value = parent._children.get(argvalue)
                if isinstance(value, SubCell) or not isinstance(value, Cell):
                    msg = "%s must be Cell, not '%s'"
                    raise TypeError(msg % (argname, type(value)))
                if par["io"] == "input":
                    value = InputCellWrapper(connection_wrapper, value)
                elif par["io"] == "edit":
                    value = EditCellWrapper(connection_wrapper, value)
                else: # par["io"] == "output"
                    node = value._get_hcell()
                    cellpath = value._path
                    overlay_node = deepcopy(node)
                    overlay_nodes[cellpath] = overlay_node
                    value = OutputCellWrapper(
                        connection_wrapper, overlay_node, cellpath
                    )
            elif par["type"] == "context":
                if isinstance(argvalue, list):
                    argvalue = tuple(argvalue)
                value = parent._children.get(argvalue)
                if value is not None:
                    msg = "'%s' must be Context, not '%s'"
                    raise TypeError(msg % (argname, type(value)))
                value = SubContext(parent, argvalue).get_graph()
            elif par["type"] == "celldict":
                value = {}
                for k,v in argvalue.items():
                    if isinstance(v, list):
                        v = tuple(v)
                    vv = parent._children.get(v)
                    if isinstance(vv, SubCell) or not isinstance(vv, Cell):
                        msg = "%s['%s'] must be Cell, not '%s'"
                        raise TypeError(msg % (argname, k, type(vv)))
                    if par["io"] == "input":
                        vv = InputCellWrapper(connection_wrapper, vv)
                    elif par["io"] == "edit":
                        vv = EditCellWrapper(connection_wrapper, vv)
                    else: # par["io"] == "output"
                        node = vv._get_hcell()
                        cellpath = vv._path
                        overlay_node = deepcopy(node)
                        overlay_nodes[cellpath] = overlay_node
                        vv = OutputCellWrapper(
                            connection_wrapper, overlay_node, cellpath
                        )
                    value[k] = vv
            elif par["type"] == "kwargs":
                value = {}
                for k,v0 in argvalue.items():
                    vtype, v = v0
                    if vtype == "cell":
                        if isinstance(v, list):
                            v = tuple(v)
                        vv = parent._children.get(v)
                        if isinstance(vv, SubCell) or not isinstance(vv, Cell):
                            msg = "%s['%s'] must be Cell, not '%s'"
                            raise TypeError(msg % (argname, k, type(vv)))
                        value[k] = "cell", InputCellWrapper(connection_wrapper, vv)
                    else: # value
                        value[k] = "value", v
            else:
                raise NotImplementedError(par["type"])                    
            namespace[argname] = value
        libctx = StaticContext.from_graph(graph, manager=parent._manager)
        namespace["libctx"] = libctx
        argnames = list(namespace.keys())
        for name in highlevel_names:
            if name not in namespace:
                namespace[name] = globals()[name]
        identifier = ".".join(self._path)
        try:
            exec_code(constructor, identifier, namespace, argnames, None)
        except Exception:
            self._get_node()["exception"] = traceback.format_exc()
            try:
                libctx.root.destroy()
            except Exception:
                pass
            return
        overlay_graph = overlay_context.get_graph()
        overlay_connections = connection_wrapper.connections
        libctx.root.destroy()
        self._get_node().pop("exception", None)
        return overlay_graph, overlay_nodes, overlay_connections

    @property
    def status(self):
        if self.exception is not None:
            return "Status: error"
        else:
            return self.ctx.status

    @property
    def exception(self):
        return self._get_node().get("exception")

    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if attr in type(self).__dict__ or attr in self.__dict__ or attr == "path":
            return super().__getattribute__(attr)
        hnode = self._get_node()
        libpath = hnode["libpath"]
        arguments = hnode["arguments"]
        lib = self.get_lib()
        params = lib["params"]        
        if attr not in arguments:
            if attr == "ctx":
                parent = self._parent()
                path = self._path + ("ctx",)
                return SynthContext(parent, path)
            if attr == "libpath":
                return libpath
            if attr == "arguments":
                return arguments
            if attr not in params or params[attr]["io"] != "output":
                raise AttributeError(attr)
        argname = attr
        parent = self._parent()
        par = params[argname]
        if par["io"] == "output":
            return Proxy(parent, self._path + (argname,), "r")
        argvalue = arguments[argname]
        if par["type"] == "cell":
            if isinstance(argvalue, list):
                argvalue = tuple(argvalue)
            value = parent._children.get(argvalue)
        else:
            value = argvalue
        return value

    def __dir__(self):        
        hnode = self._get_node()
        arguments = hnode["arguments"]
        return list(arguments.keys()) + ["ctx", "libpath", "arguments", "status"]

    def get_lib(self):
        """Returns the library of which this is an instance"""
        hnode = self._get_node()
        libpath = hnode["libpath"]
        parent = self._parent()
        lib = parent._get_lib(tuple(libpath))
        return deepcopy(lib)

    def __setattr__(self, attr, value):
        from .argument import parse_argument
        if attr.startswith("_"):
            super().__setattr__(attr, value)
            return
        hnode = self._get_node()
        arguments = hnode["arguments"]
        lib = self.get_lib()
        params = lib["params"]
        if attr not in params:
            for parname in params:
                par = params[parname]
                if par["io"] != "input":
                    continue
                if par["type"] == "kwargs":
                    if parname not in arguments:
                        arguments[parname] = {}
                    arguments[parname][attr] = parse_argument(attr, value, params[parname])
                    break
            else:
                raise AttributeError(attr)
        else:
            par = params[attr]
            if par["io"] == "output":
                raise AttributeError("Reverse assignment for '{}'".format(attr))
            arguments[attr] = parse_argument(attr, value, params[attr])
        parent = self._parent()
        parent._translate()

from .iowrappers import ConnectionWrapper, InputCellWrapper, OutputCellWrapper, EditCellWrapper
from ..synth_context import SynthContext
from ..Cell import Cell
from ..SubCell import SubCell
from ..Context import Context, SubContext
from ...midlevel.StaticContext import StaticContext
from ..Transformer import Transformer
from ..Macro import Macro
from ..Module import Module
from ...core.cached_compile import exec_code
from ..proxy import Proxy