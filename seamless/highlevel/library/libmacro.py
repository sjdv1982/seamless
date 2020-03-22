import weakref, json
from copy import deepcopy

highlevel_names = ("Context", "Cell", "Transformer", "Macro", "Reactor")

class LibMacro:

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
            "type": "libmacro",
            "libpath": self._temp_libpath,
            "arguments": self._temp_arguments,
        }
        json.dumps(node)
        ctx._graph.nodes[path] = node
        self._temp_libpath = None
        self._temp_arguments = None

    def _get_hmacro(self):
        parent = self._parent()
        return parent._graph.nodes[self._path]
        
    def _run(self):        
        assert self._path is not None 
        hmacro = self._get_hmacro()
        libpath = hmacro["libpath"]
        arguments = hmacro["arguments"]
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
                value = parent._children.get(argvalue)
                if not isinstance(value, Cell):
                    msg = "%s must be Cell, not '%s'"
                    raise TypeError(msg % (argname, type(value)))
                if par["io"] == "input":
                    value = InputCellWrapper(connection_wrapper, value)
                else: # par["io"] == "output"
                    node = value._get_hcell()
                    cellpath = value._path
                    overlay_node = deepcopy(node)
                    overlay_nodes[cellpath] = overlay_node
                    value = OutputCellWrapper(
                        connection_wrapper, overlay_node, cellpath
                    )
            else: # par["type"] == "celldict":
                value = {}
                for k,v in argvalue.items():
                    vv = parent._children.get(v)
                    if not isinstance(vv, Cell):
                        msg = "%s['%s'] must be Cell, not '%s'"
                        raise TypeError(msg % (argname, k, type(vv)))
                    if par["io"] == "input":
                        vv = InputCellWrapper(connection_wrapper, vv)
                    else: # par["io"] == "output"
                        node = vv._get_hcell()
                        cellpath = vv._path
                        overlay_node = deepcopy(node)
                        overlay_nodes[cellpath] = overlay_node
                        vv = OutputCellWrapper(
                            connection_wrapper, overlay_node, cellpath
                        )
                    value[k] = vv
            namespace[argname] = value
        libctx = StaticContext.from_graph(graph, manager=parent._manager)
        namespace["libctx"] = libctx
        argnames = list(namespace.keys())
        for name in highlevel_names:
            if name not in namespace:
                namespace[name] = globals()[name]
        identifier = ".".join(self._path)        
        exec_code(constructor, identifier, namespace, argnames, None)
        overlay_graph = overlay_context.get_graph()
        overlay_connections = connection_wrapper.connections
        libctx.root.destroy()
        return overlay_graph, overlay_nodes, overlay_connections

    @property
    def status(self):
        raise NotImplementedError

    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if attr in type(self).__dict__ or attr in self.__dict__:
            return super().__getattribute__(attr)
        hmacro = self._get_hmacro()
        libpath = hmacro["libpath"]
        arguments = hmacro["arguments"]
        if attr not in arguments:
            if attr == "ctx":
                parent = self._parent()
                path = self._path + ("ctx",)
                return LibMacroContextWrapper(parent, path)
            if attr == "libpath":
                return libpath
            if attr == "arguments":
                return arguments
            raise AttributeError(attr)
        argname = attr
        argvalue = arguments[argname]
        parent = self._parent()
        lib = parent._get_lib(tuple(libpath))
        params = lib["params"]
        par = params[argname]
        if par["type"] == "cell":        
            value = parent._children.get(argvalue)            
        else:
            value = argvalue
        return value

    def __setattr__(self, attr, value):
        from .include import get_argument_value
        if attr.startswith("_"):
            super().__setattr__(attr, value)
            return
        hmacro = self._get_hmacro()
        libpath = hmacro["libpath"]
        arguments = hmacro["arguments"]
        if attr not in arguments:
            raise AttributeError(attr)
        argname, argvalue = attr, value
        parent = self._parent()
        lib = parent._get_lib(tuple(libpath))
        params = lib["params"]
        par = params[argname]
        if par["type"] == "value":
            value = get_param_value(argvalue)
        else: # par["type"] == "cell":
            if not isinstance(argvalue, Cell):
                msg = "%s must be Cell, not '%s'"
                raise TypeError(msg % (argname, type(argvalue)))
            value = argvalue._path
        arguments[argname] = value
        parent._translate()

class LibMacroContextWrapper:
    def __init__(self, parent, path):
        self._parent = weakref.ref(parent)
        self._path = path

    @property
    def status(self):
        raise NotImplementedError

    def __dir__(self):
        path = self._path
        lp = len(path)
        parent = self._parent()
        if parent._libmacro_graph is None:
            return []
        dirs = []
        for npath in parent._libmacro_graph.nodes:
            if len(npath) > lp and npath[:lp] == path:
                dirs.append(npath[lp])
        return dirs

    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if attr in type(self).__dict__ or attr in self.__dict__:
            return super().__getattribute__(attr)
        path = self._path + (attr,)
        parent = self._parent()
        try:
            node = parent._libmacro_graph.nodes[path]
        except KeyError:
            if attr in self.__dir__():
                return LibMacroContextWrapper(parent, path)
            raise AttributeError(attr)
        if node["type"] == "cell":
            result = Cell()
        elif node["type"] == "transformer":
            result = Transformer()
        elif node["type"] == "reactor":
            result = Reactor()
        elif node["type"] == "macro":
            result = Macro()
        else:
            raise NotImplementedError(node["type"])
        Base.__init__(result, parent, path)
        return result

from .iowrappers import ConnectionWrapper, InputCellWrapper, OutputCellWrapper
from ..Base import Base
from ..Cell import Cell
from ..Context import Context#, get_status
from ...midlevel.StaticContext import StaticContext
from ..Transformer import Transformer
from ..Reactor import Reactor
from ..Macro import Macro
from ...core.cached_compile import exec_code