import weakref
from .Cell import Cell

class Transformer:
    def __init__(self, parent, path):
        self._parent = weakref.ref(parent)
        if isinstance(path, str):
            path = (path,)
        self._path = path

    def _assign_to(self, hctx, path):
        from .assign import assign_constant
        htf = self._get_htf()
        if htf["with_schema"]:
            raise NotImplementedError
        assign_constant(hctx, path, None)
        hctx._translate()


    def __setattr__(self, attr, value):
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
                raise NotImplementedError
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
