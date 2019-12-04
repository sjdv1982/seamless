import weakref
import functools
from .Cell import Cell
from .Resource import Resource
from .proxy import Proxy, CodeProxy
from .pin import InputPin, OutputPin, PinsWrapper
from .Base import Base
from .mime import language_to_mime
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
        "with_result": True,
        "SCHEMA": None, #the result schema can be exposed as an input pin to the transformer under this name. Implies with_result
        "debug": False,
        "UNTRANSLATED": True
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
        result_path = self._path + (htf["RESULT"],)
        result = OutputPin(parent, self, result_path)
        result._virtual_path = self._path
        parent._children[path] = self
        parent._children[result_path] = result

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
        result = OutputPin(parent, self, new_result_path)
        result._virtual_path = self._path
        parent._children.pop(result_path)
        parent._children[new_result_path] = result
        htf["RESULT"] = value

    @property
    def with_result(self):
        return self._get_htf()["with_result"]
    @with_result.setter
    def with_result(self, value):
        assert value in (True, False), value
        self._get_htf()["with_result"] = value
        self._parent()._translate()

    @property
    def debug(self):
        return self._get_htf()["debug"]
    @debug.setter
    def debug(self, value):
        from ..core.transformer import Transformer as CoreTransformer
        htf = self._get_htf()
        htf["debug"] = value
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
        htf["compiled"] = compiled
        htf["file_extension"] = extension
        has_translated = False
        if compiled:
            htf["with_result"] = True
            self._parent()._translate()
            has_translated = True
            tf = self._get_tf()
            tf.main_module.set({"compiler_verbose": True})
        elif lang == "docker":
            if old_language != "docker":
                im = False
                if "docker_image" not in htf["pins"]:
                    htf["pins"]["docker_image"] = default_pin.copy()
                    im = True
                if "docker_options" not in htf["pins"]:
                    htf["pins"]["docker_options"] = default_pin.copy()
                    self.docker_options = {}
                if im:
                    self.docker_image = ""

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
        return Proxy(self, ("header",), "w", getter=self._header_getter, dirs=dirs)

    @header.setter
    def header(self, value):
        htf = self._get_htf()
        assert not htf["compiled"]
        return self._setattr("header", value)

    def _header_getter(self, attr):
        htf = self._get_htf()
        assert htf["compiled"]
        tf = self._get_tf()
        if attr == "value":
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
        tf = self._get_tf()
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
        assert htf["with_result"]
        tf = self._get_tf()
        resultcell = getattr(tf, htf["RESULT"])
        result_ctx = resultcell._data._context()
        example = result_ctx.example.handle
        return example

    def add_validator(self, validator):
        htf = self._get_htf()
        inp = htf["INPUT"]
        #TODO: self.self
        return getattr(self, inp).add_validator(validator)

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
                tf = self._get_tf()
                tf.code.set(value.data)                
                translate = True
            elif isinstance(value, Proxy):
                raise AttributeError("".join(value._path))
            else:
                tf = self._get_tf()
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
                if parent._needs_translation:
                    translate = False #_get_tf() will translate
                tf = self._get_tf()
                inp = getattr(tf, htf["INPUT"])
                parent._remove_connections(self._path + (attr,))
                setattr(inp.handle_no_inference, value)
        elif attr == htf["RESULT"]:
            assert htf["with_result"]
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
                if parent._needs_translation:
                    translate = False #_get_tf() will translate
                tf = self._get_tf()
                inp = getattr(tf, htf["INPUT"])
                parent._remove_connections(self._path + (attr,))
                setattr(inp.handle_no_inference, attr, value)
        ###if parent._as_lib is not None:
        ###    parent._as_lib.needs_update = True
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

    def _get_tf(self, may_translate=True):
        parent = self._parent()
        if may_translate and not parent._translating:
            parent._do_translate()
        else:
            if not self._has_tf():
                return None
        p = parent._gen_context
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
        elif attr == htf["RESULT"]:
            assert htf["with_result"] #otherwise "result" is just a pin
            return getattr(tf, attr).value
        else:
            inp = getattr(tf, htf["INPUT"])
            p = inp.value[attr]
            return p


    @property
    def exception(self):
        htf = self._get_htf()
        tf = self._get_tf().tf
        if htf["compiled"]:
            exc = ""
            for k in ("gen_header", "integrator", "translator"):
                curr_exc = getattr(tf, k).exception
                if curr_exc is not None:
                    exc += "*** " + k + " ***\n"
                    exc += str(curr_exc)
                    exc += "*** /" + k + " ***\n"
            if not len(exc):
                return None
            return exc
        else:
            return tf.exception

    @property
    def status(self):
        htf = self._get_htf()
        tf = self._get_tf().tf
        if htf["compiled"]:
            return tf.status
        else:
            return tf.status

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        htf = self._get_htf()
        schema_mounter = None
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
            dirs = ["value", "schema", "example", "status", "exception"] + \
              list(htf["pins"].keys())
            pull_source = None
            proxycls = Proxy
        elif attr == htf["RESULT"] and htf["with_result"]:
            getter = self._resultgetter
            dirs = ["value", "schema", "example", "exception"]
            pull_source = None
            proxycls = Proxy
        elif attr == "main_module":
            if not htf["compiled"]:
                self._get_tf()
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
            tf = self._get_tf()
            return tf.code.value
        elif attr == "mount":
            return functools.partial(self._sub_mount, "code")
        elif attr == "mimetype":
            htf = self._get_htf()
            language = htf["language"]
            mimetype = language_to_mime(language)
            return mimetype
        elif attr == "checksum":
            tf = self._get_tf()
            return tf.code.checksum
        else:
            raise AttributeError(attr)

    def _inputgetter(self, attr):
        htf = self._get_htf()
        if attr in htf["pins"]:
            return getattr(self, attr)
        tf = self._get_tf()
        inputcell = getattr(tf, htf["INPUT"])
        if attr == "value":
            return inputcell.value
        elif attr == "checksum":
            return inputcell.checksum
        elif attr == "schema":
            schema = inputcell.get_schema()
            ###schema_mounter = functools.partial(self._sub_mount, "input_schema")
            schema_mounter = None ###
            return SchemaWrapper(self, schema, schema_mounter, "SCHEMA")
        elif attr == "example":
            return self.example
        elif attr == "status":
            return inputcell._data.status # TODO; take into account validation, inchannel status
        elif attr == "exception":
            return inputcell.exception
        raise AttributeError(attr)

    def _resultgetter(self, attr):
        htf = self._get_htf()
        assert htf["with_result"]
        tf = self._get_tf()
        resultcell = getattr(tf, htf["RESULT"])
        if attr == "value":
            return resultcell.value
        elif attr == "schema":
            schema = resultcell.get_schema()
            #schema_mounter = functools.partial(self._sub_mount, "result_schema")
            schema_mounter = None ###
            return SchemaWrapper(self, schema, schema_mounter, "RESULTSCHEMA")
        elif attr == "example":
            return self._result_example()
        elif attr == "exception":
            return resultcell.exception
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
        if attr == "code":
            p = tf.code
            value = p.data
            cell = {
                "path": path,
                "type": "cell",
                "celltype": "code",
                "language": language,
                "transformer": True,
            }
            if value is not None:
                assert isinstance(value, str), type(value)
                cell["TEMP"] = value
                cell["UNTRANSLATED"] = True
            if "checksum" in htf:
                htf["checksum"].pop("code", None)
        else:
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
        htf = self._get_htf()
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"].pop("input_temp", None)
        htf["checksum"].pop("input", None)
        if checksum is not None:
            htf["checksum"]["input"] = checksum

    def _observe_input_auth(self, checksum):
        if self._parent() is None:
            return
        htf = self._get_htf()
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"].pop("input_temp", None)
        htf["checksum"].pop("input_auth", None)
        if checksum is not None:
            htf["checksum"]["input_auth"] = checksum

    def _observe_input_buffer(self, checksum):
        if self._parent() is None:
            return
        htf = self._get_htf()
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"].pop("input_temp", None)
        htf["checksum"].pop("input_buffer", None)
        if checksum is not None:
            htf["checksum"]["input_buffer"] = checksum

    def _observe_code(self, checksum):
        if self._parent() is None:
            return
        htf = self._get_htf()
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"].pop("code", None)
        if checksum is not None:
            htf["checksum"]["code"] = checksum

    def _observe_result(self, checksum):
        if self._parent() is None:
            return
        htf = self._get_htf()
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"]["result"] = checksum

    def _observe_schema(self, checksum):
        if self._parent() is None:
            return
        htf = self._get_htf()
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"]["schema"] = checksum

    def _observe_result_schema(self, checksum):
        if self._parent() is None:
            return
        htf = self._get_htf()
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"]["result_schema"] = checksum

    def _observe_main_module(self, checksum):
        if self._parent() is None:
            return
        htf = self._get_htf()
        if htf.get("checksum") is None:
            htf["checksum"] = {}
        htf["checksum"]["main_module"] = checksum

    def _set_observers(self):
        htf = self._get_htf()
        if htf["compiled"] or htf["language"] not in ("python", "ipython", "bash", "docker"):
            if htf["compiled"]:
                pass
            else:
                raise NotImplementedError ### cache branch
                # NOTE: observers depend on the implementation of translate_XXX_transformer (midlevel)
        tf = self._get_tf()
        tf.code._set_observer(self._observe_code)
        inp = htf["INPUT"]
        inpcell = getattr(tf, inp)
        inpcell.auth._set_observer(self._observe_input_auth)
        inpcell.buffer._set_observer(self._observe_input_buffer)
        inpcell._data._set_observer(self._observe_input)
        schemacell = inpcell.schema
        schemacell._set_observer(self._observe_schema)
        if htf["with_result"]:
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
            std.append("main_module")
        pins = list(htf["pins"].keys())
        return sorted(d + pins + std)
