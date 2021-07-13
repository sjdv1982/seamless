import traceback
import weakref, json
from copy import deepcopy

from traitlets.traitlets import Instance

highlevel_names = ("Context", "Cell", "Transformer", "Macro", "Module")

def interpret_arguments(arguments, params, parent, extra_nodes):
    arguments = arguments.copy()
    result = {}
    for argname in params:
        par = params[argname]
        if argname not in arguments and "default" in par:
            arguments[argname] = par["default"]
    for argname, argvalue in arguments.items():
        par = params[argname]
        if par["type"] == "value":
            value = argvalue
            if value is None:
                continue
        elif par["type"] == "cell":
            path = argvalue
            if isinstance(path, list):
                path = tuple(path)
            value = None
            if path is not None:
                value = parent._children.get(path)
                if value is not None:
                    if isinstance(value, SubCell) or not isinstance(value, Cell):
                        msg = "%s must be Cell, not '%s'"
                        raise TypeError(msg % (argname, type(value)))
                    value = value._get_hcell(), path
                if value is None and extra_nodes is not None:
                    value_node = extra_nodes.get(path) 
                    if value_node is not None:
                        value = value_node, path
            if value is None:
                if path is not None:
                    raise Exception("Non-existing cell '%s'", path)
                if not (par.get("must_be_defined") == False):
                    raise ValueError("%s must be defined" % argname)
            
        elif par["type"] == "context":
            path = argvalue
            if isinstance(path, list):
                path = tuple(path)
            value = parent._children.get(path)
            if value is not None:
                msg = "'%s' must be Context, not '%s'"
                raise TypeError(msg % (argname, type(value)))
            value = SubContext(parent, path).get_graph()

        elif par["type"] == "celldict":
            value = {}
            for k,v in argvalue.items():
                if isinstance(v, list):
                    v = tuple(v)
                vv = parent._children.get(v)
                if vv is None and extra_nodes is not None:
                    value_node = extra_nodes.get(v) 
                    if value_node is not None:
                        vv = value_node, v
                else:
                    if isinstance(vv, SubCell) or not isinstance(vv, Cell):
                        msg = "%s['%s'] must be Cell, not '%s'"
                        raise TypeError(msg % (argname, k, type(vv)))
                    vv = vv._get_hcell(), v
                value[k] = vv

        elif par["type"] == "kwargs":
            if argvalue is None:
                value = None
            else:
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
                        value[k] = "cell", vv
                    else: # value
                        value[k] = "value", v

        else:
            raise NotImplementedError(par["type"])

        result[argname] = value
    return result

class LibInstance:
    
    def __init__(self, 
        parent, *, path=None, libpath=None, 
        arguments=None, extra_nodes={},
    ):
        self._parent = weakref.ref(parent)
        self._path = path
        self._temp_libpath = libpath
        self._temp_arguments = arguments
        self._overlay_context = None
        self._extra_nodes = extra_nodes
        self._bound = None

    def _bind(self, ctx, path):
        assert ctx is self._parent() or ctx._libroot is self._parent() # must have same top-level Context as the library
        if self._path is not None:
            assert self._bound is None
            assert path == self._path, (path, self._path)
        assert self._temp_libpath is not None
        assert self._temp_arguments is not None
        self._bound = weakref.ref(ctx)
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
        try:
            return parent._graph.nodes[self._path]
        except KeyError:
            try:
                return self._extra_nodes[self._path]
            except KeyError:
                raise KeyError(self._path) from None


    def _exc(self, limit, libctx):
        self._get_node()["exception"] = traceback.format_exc(limit=limit)
        if libctx is not None:
            try:
                libctx.root.destroy()
            except Exception:
                pass
        return

    def _run(self):
        assert self._path is not None
        hnode = self._get_node()
        libpath = hnode["libpath"]
        arguments = deepcopy(hnode["arguments"])
        parent = self._parent()
        lib = parent._get_lib(tuple(libpath))
        graph = lib["graph"]
        constructor = lib["constructor"]
        constructor_schema = lib.get("constructor_schema")
        params = lib["params"]

        overlay_context = Context(manager=parent._manager)
        overlay_context._libroot = parent
        overlay_context._untranslatable = True
        self._overlay_context = overlay_context
        namespace = {}
        connection_wrapper = ConnectionWrapper(self._path + ("ctx",))
        overlay_nodes = {}

        interpreted_arguments = interpret_arguments(
            arguments, params, parent,
            self._extra_nodes
        )

        # Fill namespace, part 1: value arguments
        for argname, argvalue in interpreted_arguments.items():
            par = params[argname]
            if par["type"] == "value":
                value = argvalue
            else:
                continue
            namespace[argname] = value


        # Fill namespace, part 2: validation
        if constructor_schema is not None:
            instance = LibInstanceSilk(
                data=deepcopy(namespace), 
                schema=constructor_schema
            )
            try:
                instance.validate()
            except ValidationError:
                self._exc(0, None)
                return
            except Exception:
                self._exc(None, None)
                return


        # Fill namespace, part 3: ctx and other arguments
        namespace["ctx"] = overlay_context

        for argname, argvalue in interpreted_arguments.items():
            par = params[argname]
            if par["type"] == "value":
                continue
            if argvalue is None or par["type"] == "context":
                value = argvalue
            elif par["type"] == "cell":
                node = argvalue[0]
                cellpath = argvalue[1]
                if par["io"] == "input":
                    value = InputCellWrapper(connection_wrapper, node, cellpath)
                elif par["io"] == "edit":
                    value = EditCellWrapper(connection_wrapper, node, cellpath)
                else: # par["io"] == "output"
                    overlay_node = deepcopy(node)
                    overlay_nodes[cellpath] = overlay_node
                    value = OutputCellWrapper(
                        connection_wrapper, overlay_node, cellpath
                    )
            elif par["type"] == "celldict":
                value = {}
                for k,vv in argvalue.items():
                    if par["io"] == "input":
                        vv = InputCellWrapper(connection_wrapper, vv[0], vv[1])
                    elif par["io"] == "edit":
                        vv = EditCellWrapper(connection_wrapper, vv[0], vv[1])
                    else: # par["io"] == "output"
                        node = vv[0]
                        cellpath = vv[1]
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
                        value[k] = "cell", InputCellWrapper(connection_wrapper, v)
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
        ok = False
        try:
            exec_code(constructor, identifier, namespace, argnames, None)
        except Exception:
            self._exc(1, libctx)
        else:
            ok = True
        overlay_graph = overlay_context.get_graph()
        overlay_connections = connection_wrapper.connections
        libctx.root.destroy()
        if ok:
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
        if self._bound is not None:
            hnode = self._get_node()
            libpath = hnode["libpath"]
            arguments = hnode["arguments"]
        else:
            libpath = self._temp_libpath
            arguments = self._temp_arguments
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
                if attr in self._get_api_methods():
                    api = self._build_api(arguments)
                    if not api.schema["methods"][attr].get("property"):
                        # May have false positives in non-self-modifying methods, but we can't know in advance
                        parent = self._parent()
                        parent._translate()
                    return getattr(api, attr)
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
        result = list(arguments.keys()) 
        result += ["ctx", "libpath", "arguments", "status"]
        result += self._get_api_methods()
        return sorted(result)

    def get_lib(self, copy=True):
        """Returns the library of which this is an instance"""
        if self._bound is not None:
            hnode = self._get_node()
            libpath = hnode["libpath"]
        else:
            libpath = self._temp_libpath
        parent = self._parent()
        if parent._libroot is not None:
            try:
                lib = parent._get_lib(tuple(libpath))
            except KeyError:
                try:
                    lib = parent._libroot._get_lib(tuple(libpath))
                except KeyError as exc:
                    raise exc from None
        else:
            assert libpath is not None
            lib = parent._get_lib(tuple(libpath))
        if not copy:
            return lib
        else:
            return deepcopy(lib)

    def _get_api_methods(self):
        lib = self.get_lib(copy=False)
        schema = lib.get("api_schema")
        if schema is None:
            return []
        return sorted(list(schema.get("methods", {}).keys()))

    def _build_api(self, arguments):
        lib = self.get_lib(copy=False)
        schema = lib.get("api_schema")
        assert schema is not None
        result = LibInstanceSilk(data=arguments, schema=schema)
        result._libinstance = self
        return result

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
                if attr in self._get_api_methods():
                    api = self._build_api(arguments)
                    return setattr(api, attr, value)  
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
from silk.Silk import Silk
from silk.validation import ValidationError

class LibInstanceSilk(Silk):
    __slots__ = list(Silk.__slots__) + ["_libinstance"]

    @property
    def libinstance(self):
        return self._libinstance