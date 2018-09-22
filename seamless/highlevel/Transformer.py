import weakref
import functools
from .Cell import Cell
from .Resource import Resource
from .proxy import Proxy
from .pin import InputPin, OutputPin
from .Base import Base
from .Library import test_lib_lowlevel
from ..midlevel import TRANSLATION_PREFIX
from .mime import language_to_mime
from ..core.context import Context as CoreContext

class Transformer(Base):
    def __init__(self, parent=None, path=None):
        assert (parent is None) == (path is None)
        if parent is not None:
            self._init(parent, path)

    def _init(self, parent, path):
        super().__init__(parent, path)

        htf = self._get_htf()
        result_path = self._path + (htf["RESULT"],)
        result = OutputPin(parent, self, result_path)
        result._virtual_path = self._path
        parent._children[path] = self
        parent._children[result_path] = result

    @property
    def with_schema(self):
        return self._get_htf()["with_schema"]
    @with_schema.setter
    def with_schema(self, value):
        assert value in (True, False), value
        self._get_htf()["with_schema"] = value
        self._parent()._translate()


    def _assign_to(self, hctx, path):
        from .assign import assign_connection
        tf = self._get_tf()
        htf = self._get_htf()
        if htf["with_schema"]:
            raise NotImplementedError
        parent = self._parent()
        result_path = self._path + (htf["RESULT"],)
        assign_connection(parent, result_path, path, True)
        hctx._translate()


    def __setattr__(self, attr, value):
        from .assign import assign_connection
        from ..midlevel.copying import fill_structured_cell_value
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        translate = False
        parent = self._parent()
        tf = self._get_tf()
        htf = self._get_htf()
        if attr == "code":
            assert not test_lib_lowlevel(parent, tf.code)
            if isinstance(value, Resource):
                htf["mount"] = value.filename
                htf["code"] = value.data
                translate = True
            else:
                tf.code.set(value)
                htf["code"] = tf.code.value
        else:
            inp = getattr(tf, htf["INPUT"])
            assert not test_lib_lowlevel(parent, inp)
            if attr not in htf["pins"]:
                htf["pins"][attr] = {"transfer_mode": "copy", "access_mode": "silk"}
                translate = True
            if isinstance(value, Cell):
                target_path = self._path + (attr,)
                assert value._parent() == parent
                #TODO: check existing inchannel connections (cannot be the same or higher)
                assign_connection(parent, value._path, target_path, False)
                translate = True
            else:
                if parent._needs_translation:
                    translate = False #_get_tf() will translate
                tf = self._get_tf()
                inp = getattr(tf, htf["INPUT"])
                setattr(inp.handle, attr, value)
                fill_structured_cell_value(inp, htf, "stored_state_input", "cached_state_input")
            htf.pop("in_equilibrium", None)
            if parent._as_lib is not None and not translate:
                if htf["path"] in parent._as_lib.partial_authority:
                    parent._as_lib.needs_update = True
        if translate:
            parent._translate()


    def _get_tf(self):
        parent = self._parent()
        parent.translate()
        p = getattr(parent._ctx, TRANSLATION_PREFIX)
        for subpath in self._path:
            p = getattr(p, subpath)
        assert isinstance(p, CoreContext)
        return p

    def _get_htf(self):
        parent = self._parent()
        return parent._graph[0][self._path]

    def _get_value(self, attr):
        tf = self._get_tf()
        htf = self._get_htf()
        if attr == "code":
            p = tf.code
            return p.data
        else:
            inp = getattr(tf, htf["INPUT"])
            p = inp.value[attr]
            return p


    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(value)
        htf = self._get_htf()
        if attr == htf["INPUT"]:
            # TODO: better wrapping
            return getattr(self._get_tf(), htf["INPUT"])
        if attr not in htf["pins"] and attr != "code":
            #TODO: could be result pin... what to do?
            raise AttributeError(attr)
        pull_source = functools.partial(self._pull_source, attr)
        if attr == "code":
            getter = self._codegetter
        else:
            getter = functools.partial(self._valuegetter, attr)
        return Proxy(self, (attr,), "r", pull_source=pull_source, getter=getter)

    def _codegetter(self, attr):
        if attr == "value":
            tf = self._get_tf()
            return tf.code.value
        elif attr == "mimetype":
            htf = self._get_htf()
            language = htf["language"]
            mimetype = language_to_mime(language)
            return mimetype
        else:
            raise AttributeError(attr)

    def _valuegetter(self, attr, attr2):
        if attr2 != "value":
            raise AttributeError(attr2)
        return self._get_value(attr)

    def _pull_source(self, attr, other):
        from .assign import assign_connection
        tf = self._get_tf()
        htf = self._get_htf()
        parent = self._parent()
        assert other._parent() is parent
        path = other._path
        if attr == "code":
            p = tf.code
            value = p.data
            cell = {
                "path": path,
                "type": "cell",
                "celltype": "code",
                "language": "python",
                "transformer": True,
            }
            assert isinstance(value, str)
            htf["code"] = None
        else:
            inp = getattr(tf, htf["INPUT"])
            p = getattr(inp.value, attr)
            value = p.value
            cell = {
                "path": path,
                "type": "cell",
                "celltype": "structured",
                "datatype": "mixed",
                "silk": True,
                "buffered": True,
            }
            #TODO: check existing inchannel connections (cannot be the same or higher)
        child = Cell(parent, path) #inserts itself as child
        parent._graph[0][path] = cell
        target_path = self._path + (attr,)
        assign_connection(parent, other._path, target_path, False)
        child.set(value)
        parent._translate()

    def __delattr__(self, attr):
        htf = self._get_htf()
        raise NotImplementedError #remove pin
