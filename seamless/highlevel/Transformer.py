import weakref
import functools
import pprint
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

default_pin = {
  "celltype": "mixed",
}

def new_transformer(ctx, path, code, parameters):
    if parameters is None:
        parameters = []
    for param in parameters:
        if param == "inp":
            print("WARNING: parameter 'inp' for a transformer is NOT recommended (shadows the .inp attribute)")
    transformer =    {
        "path": path,
        "type": "transformer",
        "compiled": False,
        "language": "python",
        "pins": {param:default_pin.copy() for param in parameters},
        "RESULT": "result",
        "INPUT": "inp",
        "SCHEMA": None, #the result schema can be exposed as an input pin to the transformer under this name
        "debug": False,
        "UNTRANSLATED": True,
    }
    if code is not None:
        transformer["TEMP"] = {"code": code}
    ### json.dumps(transformer)
    ctx._graph[0][path] = transformer
    return transformer


class TransformerWrapper:
    #TODO: setup access to non-pins
    def __init__(self, parent):
        self.parent = parent

class Transformer(Base):
    def __init__(self, parent=None, path=None, code=None, parameters=None):
        assert (parent is None) == (path is None)
        if parent is not None:
            self._init(parent, path, code, parameters)

    def _init(self, parent, path, code=None, parameters=None):
        super().__init__(parent, path)
        htf = new_transformer(parent, path, code, parameters)
        parent._children[path] = self

    @property
    def self(self):
        return TransformerWrapper(self)

    @property
    def RESULT(self):
        htf = self._get_htf()
        return htf["RESULT"]

    @RESULT.setter
    def RESULT(self, value):
        htf = self._get_htf()
        result_path = self._path + (htf["RESULT"],)
        new_result_path = self._path + (value,)
        parent = self._parent()
        htf["RESULT"] = value

    @property
    def debug(self):
        return self._get_htf()["debug"]
    @debug.setter
    def debug(self, value):
        assert value in (True, False)
        from ..core.transformer import Transformer as CoreTransformer
        htf = self._get_htf()
        htf["debug"] = value
        if htf.get("compiled", False):
            old_target = self.main_module.target
            if value and old_target != "debug":
                self.main_module.target = "debug"
            elif (not value) and old_target == "debug":
                self.main_module.target = "release"
        self._parent()._translate()

    @property
    def fingertip_no_remote(self):
        htf = self._get_htf()
        return htf.get("fingertip_no_remote", False)

    @fingertip_no_remote.setter
    def fingertip_no_remote(self, value):
        if value not in (True, False):
            raise TypeError(value)
        htf = self._get_htf()
        if value == True:
            htf["fingertip_no_remote"] = True
        else:
            htf.pop("fingertip_no_remote", None)

    @property
    def fingertip_no_recompute(self):
        htf = self._get_htf()
        return htf.get("fingertip_no_recompute", False)

    @fingertip_no_recompute.setter
    def fingertip_no_recompute(self, value):
        if value not in (True, False):
            raise TypeError(value)
        htf = self._get_htf()
        if value == True:
            htf["fingertip_no_recompute"] = True
        else:
            htf.pop("fingertip_no_recompute", None)

    @property
    def hash_pattern(self):
        htf = self._get_htf()
        return htf.get("hash_pattern")

    @hash_pattern.setter
    def hash_pattern(self, value):
        from ..core.protocol.deep_structure import validate_hash_pattern
        validate_hash_pattern(value)
        htf = self._get_htf()
        htf["hash_pattern"] = value
        htf.pop("checksum", None)
        self._parent()._translate()

    @property
    def language(self):
        return self._get_htf()["language"]
    @language.setter
    def language(self, value):
        from ..compiler import find_language
        lang, language, extension = find_language(value)        
        compiled = (language["mode"] == "compiled")
        htf = self._get_htf()
        old_language = htf.get("language")
        htf["language"] = lang
        old_compiled = htf.get("compiled", False)
        if old_compiled != compiled:
            htf["UNTRANSLATED"] = True
        elif (old_language in ("bash", "docker")) != (language in ("bash", "docker")):
            htf["UNTRANSLATED"] = True
        htf["compiled"] = compiled
        htf["file_extension"] = extension
        has_translated = False
        if lang == "docker":
            if old_language != "docker":
                im = False
                if "docker_image" not in htf["pins"]:
                    htf["pins"]["docker_image"] = default_pin.copy()
                    im = True
                if "docker_options" not in htf["pins"]:
                    htf["pins"]["docker_options"] = default_pin.copy()
                    self.docker_options = {}
                """
                if im:
                    self.docker_image = ""
                """

        else:
            if old_language == "docker":
                htf["pins"].pop("docker_options")
                htf["pins"].pop("docker_image")

        if not has_translated:
            self._parent()._translate()

    @property
    def header(self):
        htf = self._get_htf()
        assert htf["compiled"]
        dirs = ["value", "mount", "mimetype"]
        return HeaderProxy(self, ("header",), "w", getter=self._header_getter, dirs=dirs)

    @header.setter
    def header(self, value):
        htf = self._get_htf()
        assert not htf["compiled"]
        return self._setattr("header", value)

    def _header_getter(self, attr):
        htf = self._get_htf()
        assert htf["compiled"]        
        if attr == "value":
            tf = self._get_tf(force=True)
            return tf.header.value
        elif attr == "mount":
            return self._sub_mount_header
        elif attr == "mimetype":
            language = "c"
            mimetype = language_to_mime(language)
            return mimetype
        else:
            raise AttributeError(attr)

    @property
    def schema(self):
        htf = self._get_htf()
        inp = htf["INPUT"]
        #TODO: self.self
        return getattr(self, inp).schema

    @property
    def example(self):        
        tf = self._get_tf(force=True)
        htf = self._get_htf()
        inputcell = getattr(tf, htf["INPUT"])
        inp_ctx = inputcell._data._context()
        example = inp_ctx.example.handle
        return example

    @example.setter
    def example(self, value):
        return self.example.set(value)

    def _result_example(self):
        htf = self._get_htf()
        tf = self._get_tf(force=True)
        resultcell = getattr(tf, htf["RESULT"])
        result_ctx = resultcell._data._context()
        example = result_ctx.example.handle
        return example

    def add_validator(self, validator, name=None):
        htf = self._get_htf()
        inp = htf["INPUT"]
        #TODO: self.self
        return getattr(self, inp).add_validator(validator, name=name)

    def _assign_to(self, hctx, path):
        from .assign import assign_connection
        htf = self._get_htf()
        parent = self._parent()
        result_path = self._path + (htf["RESULT"],)
        assign_connection(parent, result_path, path, True)
        hctx._translate()

    def __setattr__(self, attr, value):
        if attr.startswith("_") or attr in type(self).__dict__:
            return object.__setattr__(self, attr, value)
        else:
            return self._setattr(attr, value)

    def _setattr(self, attr, value):
        from .assign import assign_connection
        translate = False
        parent = self._parent()
        htf = self._get_htf()

        if isinstance(value, Resource):
            assert attr ==  "code"
            self._sub_mount(attr, value.filename, "r", "file", True)

        if attr == "main_module" and htf["compiled"] and attr not in htf["pins"]:
            raise TypeError("Cannot assign directly all module objects; assign individual elements")

        if not self._has_tf() and not isinstance(value, Cell) and attr != htf["RESULT"]:
            if isinstance(value, Resource):
                value = value.data
            if "TEMP" not in htf or htf["TEMP"] is None:
                htf["TEMP"] = {}
            if "input_auth" not in htf["TEMP"]:
                htf["TEMP"]["input_auth"] = {}
            if attr == "code":
                code = value
                if callable(value):
                    code, _, _ = parse_function_code(value)
                htf["TEMP"]["code"] = code
            else:
                htf["TEMP"]["input_auth"][attr] = value
            self._parent()._translate()
            return
        
        if attr == "code":
            if isinstance(value, Cell):
                target_path = self._path + (attr,)
                assert value._parent() is parent
                assign_connection(parent, value._path, target_path, False)
                translate = True
            elif isinstance(value, Resource):
                tf = self._get_tf(force=True)
                tf.code.set(value.data)                
                translate = True
            elif isinstance(value, Proxy):
                raise AttributeError("".join(value._path))
            else:
                tf = self._get_tf(force=True)
                if callable(value):
                    value, _, _ = parse_function_code(value)
                tf.code.set(value)                
        elif attr == htf["INPUT"]:
            target_path = self._path
            if isinstance(value, Cell):
                assert value._parent() is parent
                exempt = self._exempt()
                assign_connection(parent, value._path, target_path, False, exempt=exempt)
                translate = True
            else:
                tf = self._get_tf(force=True)
                inp = getattr(tf, htf["INPUT"])
                removed = parent._remove_connections(self._path + (attr,))
                if removed:
                    translate = True
                inp.handle_no_inference.set(value)
        elif attr == htf["RESULT"]:
            result = getattr(tf, htf["RESULT"])
            # Example-based programming to set the schema
            # TODO: suppress inchannel warning
            result.handle_no_inference.set(value)
        else:
            if attr not in htf["pins"]:
                htf["pins"][attr] = default_pin.copy()
                translate = True
            if isinstance(value, Cell):
                target_path = self._path + (attr,)
                assert value._parent() is parent
                assign_connection(parent, value._path, target_path, False)
                translate = True
            else:
                tf = self._get_tf(force=True)
                inp = getattr(tf, htf["INPUT"])
                removed = parent._remove_connections(self._path + (attr,))
                if removed:
                    translate = True
                setattr(inp.handle_no_inference, attr, value)
        if translate:
            parent._translate()

    def _exempt(self):
        # assign_connection will break previous connections into self
        #  but we must exempt self.code from this, and perhaps main_module
        exempt = []
        htf = self._get_htf()
        if "code" not in htf["pins"]:
            exempt.append((self._path + ("code",)))
        if htf["compiled"] and "main_module" not in htf["pins"]:
            exempt.append((self._path + ("main_module",)))
        return exempt

    def _has_tf(self):
        htf = self._get_htf()
        if htf.get("UNTRANSLATED"):
            return False
        parent = self._parent()
        try:
            p = parent._gen_context
            for subpath in self._path:
                p = getattr(p, subpath)
            if not isinstance(p, CoreContext):
                raise AttributeError
            return True
        except AttributeError:
            return False

    def _get_tf(self, force=False):
        parent = self._parent()
        if not self._has_tf():
            if force:
                raise Exception("Transformer has not yet been translated")
            return None
        p = parent._gen_context
        for subpath in self._path:
            p = getattr(p, subpath)
        assert isinstance(p, CoreContext)
        return p

    def _get_htf(self):
        parent = self._parent()
        return parent._get_node(self._path)

    def _get_value(self, attr):
        tf = self._get_tf(force=True)
        htf = self._get_htf()
        if attr == "code":
            p = tf.code
            return p.data
        elif attr == htf["RESULT"]:
            return getattr(tf, attr).value
        else:
            inp = getattr(tf, htf["INPUT"])
            p = inp.value[attr]
            return p


    @property
    def exception(self):
        htf = self._get_htf()
        if htf.get("UNTRANSLATED"):
            return None
        tf = self._get_tf(force=True).tf
        if htf["compiled"]:            
            attrs = (
                htf["INPUT"], "code", 
                "gen_header", "integrator", "translator", 
                htf["RESULT"]
            )
        else:
            attrs = (
                htf["INPUT"], "code", 
                "tf", 
                htf["RESULT"]
            )

        exc = ""
        for k in attrs:
            if k == "code":
                code_cell = self._get_tf(force=True).code
                curr_exc = code_cell.exception
            elif k == "tf":
                if len(exc):
                    return exc
                curr_exc = tf.exception
                if curr_exc is not None:
                    return curr_exc
                else:
                    continue
            elif k in (htf["INPUT"], htf["RESULT"]):
                if len(exc):
                    return exc
                curr_exc = getattr(self, k).exception
            else:
                curr_exc = getattr(tf, k).exception
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
        htf = self._get_htf()
        if htf.get("UNTRANSLATED"):
            return None
        tf = self._get_tf(force=True).tf
        if htf["compiled"]:            
            attrs = (
                htf["INPUT"], "code", 
                "gen_header", "integrator", "translator", 
                htf["RESULT"]
            )
        else:
            attrs = (
                htf["INPUT"], "code", 
                "tf", 
                htf["RESULT"]
            )
        for k in attrs:
            if k in (htf["INPUT"], htf["RESULT"]):
                cell = getattr(self, k)
                status = cell.status
            elif k == "code":
                status = self._get_tf(force=True).code.status
            elif k == "tf":
                status = self._get_tf(force=True).tf.status
            else:
                tf = self._get_tf(force=True).tf
                status = getattr(tf, k).status
            if not status.endswith("OK"):
                return "*" + k + "*: " + status
        return "Status: OK"

    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if attr in type(self).__dict__ or attr in self.__dict__:
            return super().__getattribute__(attr)
        htf = self._get_htf()
        dirs = None
        pull_source = functools.partial(self._pull_source, attr)
        if attr in htf["pins"]:
            getter = functools.partial(self._valuegetter, attr)
            dirs = ["value"]
            proxycls = Proxy
        elif attr == "pins":
            return PinsWrapper(self)
        elif attr == "code":
            getter = self._codegetter
            dirs = ["value", "mount", "mimetype"]
            proxycls = CodeProxy
        elif attr == htf["INPUT"]:
            getter = self._inputgetter
            dirs = [
              "value", "buffered", "data", "checksum",
              "schema", "example", "status", "exception",
              "add_validator", "handle"
            ] + list(htf["pins"].keys())
            pull_source = None
            proxycls = Proxy
        elif attr == htf["RESULT"]:
            getter = self._resultgetter
            dirs = [
              "value", "buffered", "data", "checksum",
              "schema", "example", "exception", 
              "add_validator"
            ]
            pull_source = None
            proxycls = Proxy
        elif attr == "main_module":
            if not htf["compiled"]:
                raise AttributeError(attr)
            if htf["compiled"]:
                return CompiledObjectDict(self)
        else:
            raise AttributeError(attr)
        return proxycls(self, (attr,), "r", pull_source=pull_source, getter=getter, dirs=dirs)

    def _sub_mount_header(self, path=None, mode="w", authority="cell", persistent=True):
        assert mode == "w"
        assert authority == "cell"
        return self._sub_mount(
          "header",
          path=path,
          mode=mode,
          authority=authority,
          persistent=persistent
        )

    def _sub_mount(self, attr, path=None, mode="rw", authority="cell", persistent=True):
        htf = self._get_htf()
        if attr == "header":
            assert htf["compiled"]
        if path is None:
            if "mount" in htf:
                mount = htf["mount"]
                if attr in mount:
                    mount.pop(attr)
                    if not len(mount):
                        htf.pop("mount")
            return
        mount = {
            "path": path,
            "mode": mode,
            "authority": authority,
            "persistent": persistent
        }
        if not "mount" in htf:
            htf["mount"] = {}
        htf["mount"][attr] = mount
        self._parent()._translate()

    def _codegetter(self, attr):
        if attr == "value":
            tf = self._get_tf(force=True)            
            return tf.code.value
        elif attr == "mount":
            return functools.partial(self._sub_mount, "code")
        elif attr == "mimetype":
            htf = self._get_htf()
            language = htf["language"]
            mimetype = language_to_mime(language)
            return mimetype
        elif attr == "checksum":
            tf = self._get_tf(force=True)
            return tf.code.checksum
        else:
            raise AttributeError(attr)

    def _inputgetter(self, attr):
        htf = self._get_htf()
        if attr in htf["pins"]:
            return getattr(self, attr)
        tf = self._get_tf(force=True)
        inputcell = getattr(tf, htf["INPUT"])
        if attr == "value":
            return inputcell.value
        elif attr == "data":
            return inputcell.data
        elif attr == "buffered":
            return inputcell.buffer.value
        elif attr == "checksum":
            return inputcell.checksum
        elif attr == "handle":
            return inputcell.handle_no_inference
        elif attr == "schema":
            #schema = inputcell.get_schema() # WRONG
            inp_ctx = inputcell._data._context()
            schema = inp_ctx.example.handle.schema
            return SchemaWrapper(self, schema, "SCHEMA")
        elif attr == "example":
            return self.example
        elif attr == "status":
            return inputcell._data.status # TODO; take into account validation, inchannel status
        elif attr == "exception":
            return inputcell.exception
        elif attr == "add_validator":
            handle = inputcell.handle_no_inference
            return handle.add_validator
        raise AttributeError(attr)

    def _resultgetter(self, attr):
        htf = self._get_htf()
        tf = self._get_tf(force=True)
        resultcell = getattr(tf, htf["RESULT"])
        if attr == "mount":
            raise Exception("Result cells cannot be mounted")
        if attr == "value":
            return resultcell.value
        elif attr == "data":
            return resultcell.data
        elif attr == "buffered":
            return resultcell.buffer.value
        elif attr == "checksum":
            return resultcell.checksum
        elif attr == "schema":
            ###schema = resultcell.get_schema() #wrong!
            result_ctx = resultcell._data._context()
            schema = result_ctx.example.handle.schema
            return SchemaWrapper(self, schema, "RESULTSCHEMA")
        elif attr == "example":
            return self._result_example()
        elif attr == "exception":
            return resultcell.exception
        elif attr == "add_validator":
            result_ctx = resultcell._data._context()
            handle = result_ctx.example.handle
            return handle.add_validator
        return getattr(resultcell, attr)

    def _valuegetter(self, attr, attr2):
        if attr2 != "value":
            raise AttributeError(attr2)
        return self._get_value(attr)

    def _pull_source(self, attr, other):
        from .assign import assign_connection
        tf = self._get_tf()
        htf = self._get_htf()
        parent = self._parent()
        if isinstance(other, Cell):
            target_path = self._path + (attr,)
            assign_connection(parent, other._path, target_path, False)
            parent._translate()
            return
        assert isinstance(other, Proxy)
        assert other._parent() is parent
        path = other._path
        language = htf["language"]
        value = None
        if attr == "code":
            if tf is not None:
                p = tf.code
                value = p.data
            elif "TEMP" in htf and "code" in htf["TEMP"]:
                value = htf["TEMP"]["code"]
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
            if "checksum" in htf:
                htf["checksum"].pop("code", None)
        else:
            raise NotImplementedError
            if tf is not None:
                inp = getattr(tf, htf["INPUT"])
                p = getattr(inp.value, attr)
            value = p.value
            cell = {
                "path": path,
                "type": "cell",
                "celltype": "structured",
                "datatype": "mixed",
            }
        child = Cell(parent, path) #inserts itself as child
        parent._graph[0][path] = cell
        if "file_extension" in htf:
            child.mimetype = htf["file_extension"]
        else:
            mimetype = language_to_mime(language)
            child.mimetype = mimetype

        target_path = self._path + (attr,)
        assign_connection(parent, other._path, target_path, False)
        parent._translate()

    def _observe_input(self, checksum):
        if self._parent() is None:
            return
        try:
            htf = self._get_htf()
        except Exception:
            return
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"].pop("input_temp", None)
        htf["checksum"].pop("input", None)
        if checksum is not None:
            htf["checksum"]["input"] = checksum

    def _observe_input_auth(self, checksum):
        if self._parent() is None:
            return
        try:
            htf = self._get_htf()
        except Exception:
            return
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"].pop("input_temp", None)
        htf["checksum"].pop("input_auth", None)
        if checksum is not None:
            htf["checksum"]["input_auth"] = checksum

    def _observe_input_buffer(self, checksum):
        if self._parent() is None:
            return
        try:
            htf = self._get_htf()
        except Exception:
            return
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"].pop("input_temp", None)
        htf["checksum"].pop("input_buffer", None)
        if checksum is not None:
            htf["checksum"]["input_buffer"] = checksum

    def _observe_code(self, checksum):
        if self._parent() is None:
            return
        try:
            htf = self._get_htf()
        except Exception:
            return
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"].pop("code", None)
        if checksum is not None:
            htf["checksum"]["code"] = checksum

    def _observe_result(self, checksum):
        if self._parent() is None:
            return
        try:
            htf = self._get_htf()
        except Exception:
            return
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"]["result"] = checksum

    def _observe_schema(self, checksum):
        if self._parent() is None:
            return
        try:
            htf = self._get_htf()
        except Exception:
            return
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"]["schema"] = checksum

    def _observe_result_schema(self, checksum):
        if self._parent() is None:
            return
        try:
            htf = self._get_htf()
        except Exception:
            return
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"]["result_schema"] = checksum

    def _observe_main_module(self, checksum):
        if self._parent() is None:
            return
        try:
            htf = self._get_htf()
        except Exception:
            return
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"]["main_module"] = checksum

    def _set_observers(self):
        htf = self._get_htf()
        if htf["compiled"] or htf["language"] not in ("python", "ipython", "bash", "docker"):
            if htf["compiled"]:
                pass
            else:
                raise NotImplementedError # NOTE: observers depend on the implementation of translate_XXX_transformer (midlevel)
        tf = self._get_tf(force=True)
        tf.code._set_observer(self._observe_code)
        inp = htf["INPUT"]
        inpcell = getattr(tf, inp)
        inpcell.auth._set_observer(self._observe_input_auth)
        inpcell.buffer._set_observer(self._observe_input_buffer)
        inpcell._data._set_observer(self._observe_input)
        schemacell = inpcell.schema
        schemacell._set_observer(self._observe_schema)
        result = htf["RESULT"]
        resultcell = getattr(tf, result)
        resultcell._data._set_observer(self._observe_result)
        schemacell = resultcell.schema
        schemacell._set_observer(self._observe_result_schema)
        if htf["compiled"]:
            tf.main_module._data._set_observer(self._observe_main_module)


    def __delattr__(self, attr):
        htf = self._get_htf()
        raise NotImplementedError #remove pin

    def __dir__(self):
        htf = self._get_htf()
        d = super().__dir__()
        std = ["code", "pins", htf["RESULT"] , htf["INPUT"], "exception", "status"]
        if htf["compiled"]:
            std += list(("main_module", "header"))
        pins = list(htf["pins"].keys())
        return sorted(d + pins + std)
