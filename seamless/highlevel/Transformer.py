import weakref
import functools
from .Cell import Cell
from .proxy import Proxy
from .pin import InputPin, OutputPin

class Transformer:
    def __init__(self, parent, path):
        self._parent = weakref.ref(parent)
        if isinstance(path, str):
            path = (path,)
        self._path = path

        htf = self._get_htf()
        result_path = self._path + (htf["RESULT"],)
        result = OutputPin(parent, self, result_path)
        result._virtual_path = self._path
        parent._children[path] = self
        parent._children[result_path] = result


    def _assign_to(self, hctx, path):
        from .assign import assign_constant, assign_connection
        tf = self._get_tf()
        htf = self._get_htf()
        if htf["with_schema"]:
            raise NotImplementedError
        parent = self._parent()
        htf = self._get_htf()
        result_path = self._path + (htf["RESULT"],)
        assign_connection(parent, result_path, path, True)
        hctx._translate()

    def __setattr__(self, attr, value):
        from .assign import assign_connection
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        translate = False
        parent = self._parent()
        if attr == "code":
            tf = self._get_tf()
            htf = self._get_htf()
            tf.code.set(value)
            htf["code"] = tf.code.value
        else:
            htf = self._get_htf()
            if attr not in htf["pins"]:
                htf["pins"][attr] = {"submode": "silk"}
                translate = True
            if isinstance(value, Cell):
                target_path = self._path + (attr,)
                assert value._parent() == parent
                #TODO: check existing inchannel connections (cannot be the same or higher)
                assign_connection(parent, value._path, target_path, False)
                translate = True
            else:
                htf["values"][(attr,)] = value
                tf = self._get_tf()
                inp = tf.inp.handle
                setattr(inp, attr, value)
            if translate:
                parent._translate()

    def _get_tf(self):
        parent = self._parent()
        parent.translate()
        p = parent._ctx.translated
        for subpath in self._path:
            p = getattr(p, subpath)
        return p

    def _get_htf(self):
        parent = self._parent()
        return parent._graph[0][self._path]

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(value)
        htf = self._get_htf()
        if attr not in htf["pins"] and attr != "code":
            #TODO: could be result pin... what to do?
            raise AttributeError(attr)
        #TODO: make it a full wrapper of the input pin value, with sub-attribute access, modify tf["values"] when set
        pull_source = functools.partial(self._pull_source, attr)
        return Proxy(self, (attr,), "r", pull_source)

    def _pull_source(self, attr, other):
        from .assign import assign_connection
        tf = self._get_tf()
        htf = self._get_htf()
        parent = self._parent()
        assert other._parent() is parent
        path = other._path
        if attr == "code":
            p = tf.code
            value = p.value
            cell = {
                "path": path,
                "type": "cell",
                "celltype": "code",
                "language": "python",
                "transformer": True,
                "value": value,
            }
            htf["code"] = None
        else:
            inp = getattr(tf, htf["INPUT"])
            p = getattr(inp, attr)
            value = p.value
            cell = {
                "path": path,
                "type": "cell",
                "celltype": "structured",
                "format": "mixed",
                "silk": True,
                "buffered": True,
                "value": value,
                "schema": None,
            }
            #TODO: elim attribute from htf["values"]
            #TODO: check existing inchannel connections (cannot be the same or higher)
        Cell(parent, path) #inserts itself as child
        parent._graph[0][path] = cell
        target_path = self._path + (attr,)
        assign_connection(parent, other._path, target_path, False)
        parent._translate()

    def __delattr__(self, attr):
        htf = self._get_htf()
        raise NotImplementedError #remove pin

    def _destroy(self):
        p = self._path
        nodes, connections = parent._graph
        for nodename in list(nodes.keys()):
            if nodename.startswith(p):
                nodes.pop(nodename)
        for con in list(connections):
            if con["source"].startswith(p) or con["target"].startswith(p):
                connections.remove(con)
