import weakref
from .Cell import Cell
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
        assign_connection(parent, result_path, path)
        hctx._translate()

    def __setattr__(self, attr, value):
        from .assign import assign_connection
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        parent = self._parent()
        if attr == "code":
            raise NotImplementedError
        else:
            htf = self._get_htf()
            if attr not in htf["pins"]:
                htf["pins"] = {"submode": "silk"}
            if isinstance(value, Cell):
                htf = self._get_htf()
                result_path = self._path + (htf["RESULT"],)
                assign_connection(parent, result_path, value._path)
                parent._translate()
                return

            htf["values"][(attr,)] = value

            tf = self._get_tf()
            inp = tf.inp.handle
            setattr(inp, attr, value)

    def _get_tf(self):
        parent = self._parent()
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
        if attr not in htf["pins"]:
            #TODO: could be result pin... what to do?
            raise AttributeError(value)
        raise NotImplementedError #get a wrapper of the input pin value, with sub-attribute access, modify tf["values"] when set

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
