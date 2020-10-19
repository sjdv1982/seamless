import weakref
import functools
import pprint
from copy import deepcopy
from .Cell import Cell
from .Resource import Resource
from .proxy import Proxy, CodeProxy, HeaderProxy
from .pin import PinsWrapper
from .Base import Base
from ..mime import language_to_mime
from ..core.context import Context as CoreContext
from . import parse_function_code
from .SchemaWrapper import SchemaWrapper
from ..silk import Silk
from .compiled import CompiledObjectDict
from ..mixed.get_form import get_form

default_pin = {
  "io": "parameter",
  "celltype": "mixed",
}

def new_macro(ctx, path, code, pins):
    if pins is None:
        pins = []
    for pin in pins:
        if pin == "param":
            print("WARNING: pin 'param' for a macro is NOT recommended (shadows the .param attribute)")
    if isinstance(pins, (list, tuple)):
        pins = {pin:default_pin.copy() for pin in pins}
    else:
        pins = deepcopy(pins)
    macro = {
        "path": path,
        "type": "macro",
        "language": "python",
        "pins": pins,
        "PARAM": "parameter",
        "UNTRANSLATED": True,
        "elision": False,
    }
    if code is not None:
        macro["TEMP"] = {"code": code}
    ctx._graph[0][path] = macro
    return macro

class Macro(Base):
    _temp_code = None
    _temp_pins = None
    def __init__(self, *, parent=None, path=None, code=None, pins=None):
        assert (parent is None) == (path is None)
        if parent is not None:
            self._init(parent, path, code, pins)
        else:
            self._temp_code = code
            self._temp_pins = pins

    def _init(self, parent, path, code=None, pins=None):
        super().__init__(parent, path)
        if self._temp_code is not None:
            assert code is None
            code = self._temp_code
        if self._temp_pins is not None:
            assert pins is None
            pins = self._temp_pins
        try:
            assert code is None
            assert pins is None
            node = self._get_node()
        except:
            node = None
        if node is None:
            node = new_macro(parent, path, code, pins)
        parent._children[path] = self

    @property
    def self(self):
        raise NotImplementedError

    @property
    def ctx(self):
        mctx = self._get_mctx()
        if mctx is None:
            return None
        return mctx.macro.ctx

    @property
    def macro(self):
        return self

    @property
    def schema(self):
        node = self._get_node()
        param = node["PARAM"]
        #TODO: self.self
        return getattr(self, param).schema

    @property
    def example(self):
        mctx = self._get_mctx(force=True)
        node = self._get_node()
        paramcell = getattr(mctx, node["PARAM"])
        param_ctx = paramcell._data._context()
        example = param_ctx.example.handle
        return example

    @example.setter
    def example(self, value):
        return self.example.set(value)

    @property
    def elision(self):
        node = self._get_node()
        return node["elision"]

    @elision.setter
    def elision(self, value):
        assert isinstance(value, bool)
        node = self._get_node()
        node["elision"] = value

    def add_validator(self, validator, name):
        """Adds a validator to the input, analogous to Cell.add_validator"""
        node = self._get_node()
        param = node["PARAM"]
        #TODO: self.self
        return getattr(self, param).add_validator(validator, name=name)

    def __setattr__(self, attr, value):
        if attr.startswith("_") or attr in type(self).__dict__:
            return object.__setattr__(self, attr, value)
        else:
            return self._setattr(attr, value)

    def _setattr(self, attr, value):
        from .assign import assign_connection
        translate = False
        parent = self._parent()
        node = self._get_node()

        if attr != "code":
            if attr not in node["pins"]:
                node["pins"][attr] = default_pin.copy()
            else:
                if not isinstance(value, Cell):
                    pin = node["pins"][attr]
                    if pin["io"] != "parameter":
                        raise Exception("Can only assign value to parameter pin")

        if isinstance(value, Resource):
            assert attr == "code"
            self._sub_mount(attr, value.filename, "r", "file", True)

        if not self._has_mctx() and not isinstance(value, Cell):
            if isinstance(value, Resource):
                value = value.data
            if "TEMP" not in node or node["TEMP"] is None:
                node["TEMP"] = {}
            if "param_auth" not in node["TEMP"]:
                node["TEMP"]["param_auth"] = {}
            if attr == "code":
                code = value
                if callable(value):
                    code, _, _ = parse_function_code(value)
                node["TEMP"]["code"] = code
            else:
                get_form(value)
                node["TEMP"]["param_auth"][attr] = value
            self._parent()._translate()
            return

        if attr == "code":
            if isinstance(value, Cell):
                target_path = self._path + (attr,)
                assert value._parent() is parent
                assign_connection(parent, value._path, target_path, False)
                translate = True
            elif isinstance(value, Resource):
                mctx = self._get_mctx(force=True)
                mctx.code.set(value.data)
                translate = True
            elif isinstance(value, Proxy):
                raise AttributeError("".join(value._path))
            else:
                mctx = self._get_mctx(force=True)
                if callable(value):
                    value, _, _ = parse_function_code(value)
                mctx.code.set(value)
        else:
            if attr not in node["pins"]:
                node["pins"][attr] = default_pin.copy()
                translate = True
            pin = node["pins"][attr]
            if pin["io"] == "output":
                raise AttributeError(
                  "Cannot assign to output pin '{}'".format(attr)
                )
            if isinstance(value, Cell):
                target_path = self._path + (attr,)
                assert value._parent() is parent
                assign_connection(parent, value._path, target_path, False)
                translate = True
            else:
                mctx = self._get_mctx(force=True)
                param = getattr(mctx, node["PARAM"])
                removed = parent._remove_connections(self._path + (attr,))
                if removed:
                    translate = True
                setattr(param.handle_no_inference, attr, value)
        if translate:
            parent._translate()

    def _exempt(self):
        # assign_connection will break previous connections into self
        #  but we must exempt self.code from this
        exempt = []
        node = self._get_node()
        if "code" not in node["pins"]:
            exempt.append((self._path + ("code",)))
        return exempt

    def _has_mctx(self):
        node = self._get_node()
        if node.get("UNTRANSLATED"):
            return False
        parent = self._parent()
        try:
            p = parent._gen_context
            for subpath in self._path:
                p2 = getattr(p, subpath)
                if isinstance(p2, SynthContext) and p2._context is not None:
                    p2 = p2._context()
                p = p2
            if not isinstance(p, CoreContext):
                raise AttributeError
            return True
        except AttributeError:
            return False

    def _get_mctx(self, force=False):
        parent = self._parent()
        if not self._has_mctx():
            if force:
                raise Exception("Transformer has not yet been translated")
            return None
        p = parent._gen_context
        for subpath in self._path:
            p2 = getattr(p, subpath)
            if isinstance(p2, SynthContext) and p2._context is not None:
                p2 = p2._context()
            p = p2
        assert isinstance(p, CoreContext)
        return p

    def _get_node(self):
        parent = self._parent()
        return parent._get_node(self._path)

    def _get_value(self, attr):
        mctx = self._get_mctx(force=True)
        node = self._get_node()
        if attr == "code":
            p = mctx.code
            return p.data
        else:
            param = getattr(mctx, node["PARAM"])
            p = param.value[attr]
            return p

    @property
    def exception(self):
        node = self._get_node()
        if node.get("UNTRANSLATED"):
            return None
        macro = self._get_mctx(force=True).macro
        attrs = (
            node["PARAM"],
            "code",
            "macro",
        )

        exc = ""
        for k in attrs:
            if k == "code":
                code_cell = self._get_mctx(force=True).code
                curr_exc = code_cell.exception
            elif k == "macro":
                if len(exc):
                    return exc
                curr_exc = macro.exception
                if curr_exc is not None:
                    return curr_exc
                else:
                    continue
            elif k == node["PARAM"]:
                if len(exc):
                    return exc
                curr_exc = getattr(self, k).exception
            else:
                curr_exc = getattr(macro, k).exception
            if curr_exc is not None:
                if isinstance(curr_exc, dict):
                    curr_exc = pprint.pformat(curr_exc, width=100)
                exc += "*** " + k + " ***\n"
                exc += str(curr_exc)
                exc += "*** /" + k + " ***\n"
        if not len(exc):
            return None
        return exc

    @property
    def status(self):
        node = self._get_node()
        if node.get("UNTRANSLATED"):
            return None
        macro = self._get_mctx(force=True).macro
        attrs = (
            node["PARAM"],
            "code",
            "macro",
        )
        for k in attrs:
            if k == node["PARAM"]:
                cell = getattr(self, k)
                status = cell.status
            elif k == "code":
                status = self._get_mctx(force=True).code.status
            elif k == "macro":
                status = self._get_mctx(force=True).macro.status
            else:
                macro = self._get_mctx(force=True).macro
                status = getattr(mctx, k).status
            if not status.endswith("OK"):
                return "*" + k + "*: " + status
        return "Status: OK"

    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if attr in type(self).__dict__ or attr in self.__dict__:
            return super().__getattribute__(attr)
        node = self._get_node()
        dirs = None
        pull_source = functools.partial(self._pull_source, attr)
        if attr in node["pins"]:
            getter = functools.partial(self._valuegetter, attr)
            dirs = ["value"]
            proxycls = Proxy
        elif attr == "pins":
            return PinsWrapper(self)
        elif attr == "code":
            getter = self._codegetter
            dirs = ["value", "mount", "mimetype"]
            proxycls = CodeProxy
        elif attr == node["PARAM"]:
            getter = self._paramgetter
            dirs = [
              "value", "buffered", "data", "checksum",
              "schema", "example", "status", "exception",
              "add_validator", "handle"
            ] + list(node["pins"].keys())
            pull_source = None
            proxycls = Proxy
        else:
            raise AttributeError(attr)
        return proxycls(self, (attr,), "r", pull_source=pull_source, getter=getter, dirs=dirs)

    def _sub_mount(self, attr, path=None, mode="rw", authority="cell", persistent=True):
        node = self._get_node()
        if path is None:
            if "mount" in node:
                mount = node["mount"]
                if attr in mount:
                    mount.pop(attr)
                    if not len(mount):
                        node.pop("mount")
            return
        mount = {
            "path": path,
            "mode": mode,
            "authority": authority,
            "persistent": persistent
        }
        if not "mount" in node:
            node["mount"] = {}
        node["mount"][attr] = mount
        self._parent()._translate()

    def _codegetter(self, attr):
        if attr == "value":
            mctx = self._get_mctx(force=True)
            return mctx.code.value
        elif attr == "mount":
            return functools.partial(self._sub_mount, "code")
        elif attr == "mimetype":
            node = self._get_node()
            language = node["language"]
            mimetype = language_to_mime(language)
            return mimetype
        elif attr == "checksum":
            mctx = self._get_mctx(force=True)
            return mctx.code.checksum
        else:
            raise AttributeError(attr)

    def _paramgetter(self, attr):
        node = self._get_node()
        if attr in node["pins"]:
            return getattr(self, attr)
        mctx = self._get_mctx(force=True)
        paramcell = getattr(mctx, node["PARAM"])
        if attr == "value":
            return paramcell.value
        elif attr == "data":
            return paramcell.data
        elif attr == "buffered":
            return paramcell.buffer.value
        elif attr == "checksum":
            return paramcell.checksum
        elif attr == "handle":
            return paramcell.handle_no_inference
        elif attr == "schema":
            #schema = paramcell.get_schema() # WRONG
            param_ctx = paramcell._data._context()
            schema = param_ctx.example.handle.schema
            return SchemaWrapper(self, schema, "SCHEMA")
        elif attr == "example":
            return self.example
        elif attr == "status":
            return paramcell._data.status # TODO; take into account validation, inchannel status
        elif attr == "exception":
            return paramcell.exception
        elif attr == "add_validator":
            handle = paramcell.handle_no_inference
            return handle.add_validator
        raise AttributeError(attr)

    def _valuegetter(self, attr, attr2):
        if attr2 != "value":
            raise AttributeError(attr2)
        return self._get_value(attr)

    def _pull_source(self, attr, other):
        raise NotImplementedError # TODO: follow transformer
        from .assign import assign_connection
        mctx = self._get_mctx()
        node = self._get_node()
        parent = self._parent()
        if isinstance(other, Cell):
            target_path = self._path + (attr,)
            assign_connection(parent, other._path, target_path, False)
            parent._translate()
            return
        assert isinstance(other, Proxy)
        assert other._parent() is parent
        path = other._path
        language = node["language"]
        value = None
        if attr == "code":
            if mctx is not None:
                p = mctx.code
                value = p.data
            elif "TEMP" in node and "code" in node["TEMP"]:
                value = node["TEMP"]["code"]
            cell = {
                "path": path,
                "type": "cell",
                "celltype": "code",
                "language": language,
                "transformer": True,
                "UNTRANSLATED": True,
            }
            if value is not None:
                assert isinstance(value, str), type(value)
                cell["TEMP"] = value
            if "checksum" in node:
                node["checksum"].pop("code", None)
        else:
            raise NotImplementedError
            if mctx is not None:
                param = getattr(mctx, node["PARAM"])
                p = getattr(param.value, attr)
            value = p.value
            cell = {
                "path": path,
                "type": "cell",
                "celltype": "structured",
                "datatype": "mixed",
            }
        child = Cell(parent=ctx, path=path) #inserts itself as child
        parent._graph[0][path] = cell
        if "file_extension" in node:
            child.mimetype = node["file_extension"]
        else:
            mimetype = language_to_mime(language)
            child.mimetype = mimetype

        target_path = self._path + (attr,)
        assign_connection(parent, other._path, target_path, False)
        parent._translate()

    def _observe_param(self, checksum):
        if self._parent() is None:
            return
        try:
            node = self._get_node()
        except Exception:
            return
        if node.get("checksum") is None:
            node["checksum"] = {}
        node["checksum"].pop("param_temp", None)
        node["checksum"].pop("param", None)
        if checksum is not None:
            node["checksum"]["param"] = checksum

    def _observe_param_auth(self, checksum):
        if self._parent() is None:
            return
        try:
            node = self._get_node()
        except Exception:
            return
        if node.get("checksum") is None:
            node["checksum"] = {}
        node["checksum"].pop("param_temp", None)
        node["checksum"].pop("param_auth", None)
        if checksum is not None:
            node["checksum"]["param_auth"] = checksum

    def _observe_param_buffer(self, checksum):
        if self._parent() is None:
            return
        try:
            node = self._get_node()
        except Exception:
            return
        if node.get("checksum") is None:
            node["checksum"] = {}
        node["checksum"].pop("param_temp", None)
        node["checksum"].pop("param_buffer", None)
        if checksum is not None:
            node["checksum"]["param_buffer"] = checksum

    def _observe_code(self, checksum):
        if self._parent() is None:
            return
        try:
            node = self._get_node()
        except Exception:
            return
        if node.get("checksum") is None:
            node["checksum"] = {}
        node["checksum"].pop("code", None)
        if checksum is not None:
            node["checksum"]["code"] = checksum

    def _observe_schema(self, checksum):
        if self._parent() is None:
            return
        try:
            node = self._get_node()
        except Exception:
            return
        if node.get("checksum") is None:
            node["checksum"] = {}
        node["checksum"]["schema"] = checksum


    def _set_observers(self):
        node = self._get_node()
        mctx = self._get_mctx(force=True)
        mctx.code._set_observer(self._observe_code)
        param = node["PARAM"]
        paramcell = getattr(mctx, param)
        paramcell.auth._set_observer(self._observe_param_auth)
        paramcell.buffer._set_observer(self._observe_param_buffer)
        paramcell._data._set_observer(self._observe_param)
        schemacell = paramcell.schema
        schemacell._set_observer(self._observe_schema)

    def __delattr__(self, attr):
        node = self._get_node()
        raise NotImplementedError #remove pin

    def __dir__(self):
        node = self._get_node()
        d = super().__dir__()
        std = ["code", "pins", node["PARAM"], "exception", "status"]
        pins = list(node["pins"].keys())
        return sorted(d + pins + std)

from .synth_context import SynthContext