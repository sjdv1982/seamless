from seamless.metalevel.debugmode import DebugMode
import weakref
import functools
import pprint
import json
from copy import deepcopy
from .Cell import Cell
from .Module import Module
from .Resource import Resource
from .SelfWrapper import SelfWrapper
from .proxy import Proxy, CodeProxy, HeaderProxy
from .pin import PinsWrapper
from .Base import Base
from ..mime import language_to_mime
from ..core.context import Context as CoreContext
from . import parse_function_code
from .SchemaWrapper import SchemaWrapper
from silk import Silk
from .compiled import CompiledObjectDict
from silk.mixed.get_form import get_form
from .Environment import Environment

# removed celltype="mixed" as of Seamless 0.7
default_pin = {
  
}

def new_transformer(ctx, path, code, pins, hash_pattern):
    if pins is None:
        pins = []
    if isinstance(pins, (list, tuple)):
        pins = {pin:default_pin.copy() for pin in pins}
    else:
        pins = deepcopy(pins)
    for pin in pins:
        if pin == "inp":
            print("WARNING: pin 'inp' for a transformer is NOT recommended (shadows the .inp attribute)")
    transformer =    {
        "path": path,
        "type": "transformer",
        "compiled": False,
        "language": "python",
        "pins": pins,
        "hash_pattern": hash_pattern,
        "RESULT": "result",
        "INPUT": "inp",
        "SCHEMA": None, #the result schema can be exposed as an input pin to the transformer under this name
        "UNTRANSLATED": True,
    }
    if code is not None:
        transformer["TEMP"] = {"code": code}
    ### json.dumps(transformer)
    ctx._graph[0][path] = transformer
    return transformer

class Transformer(Base):
    """Transforms input values to a result value

    See http://sjdv1982.github.io/seamless/sphinx/html/transformer.html for documentation
    """
    _temp_code = None
    _temp_pins = None
    def __init__(self, *, parent=None, path=None, code=None, pins=None, hash_pattern={"*": "#"}):
        from ..metalevel.debugmode import DebugMode
        assert (parent is None) == (path is None)
        if parent is not None:
            self._init(parent, path, code, pins)
        else:
            self._temp_code = code
            self._temp_pins = pins
        self._debug = DebugMode(self)

    def _init(self, parent, path, code=None, pins=None, hash_pattern={"*": "#"}):
        super().__init__(parent, path)
        if self._temp_code is not None:
            assert code is None
            code = self._temp_code
        if self._temp_pins is not None:
            assert pins is None
            pins = self._temp_pins
        parent._children[path] = self
        try:
            assert code is None
            assert pins is None
            assert hash_pattern == {"*": "#"}
            node = self._get_htf()
        except:
            node = None
        self._environment = Environment(self)
        if node is None:
            htf = new_transformer(parent, path, code, pins, hash_pattern)
        elif "environment" in node:
            self._environment._load(node["environment"])
        self._temp_code = None
        self._temp_pins = None

    @property
    def environment(self):
        return self._environment

    @property
    def debug(self):
        return self._debug

    @property
    def meta(self):
        """Dictionary of meta-parameters.
These don't affect the computation result, but may affect job managers
Example of meta-parameters: expected computation time, service name

You can set this dictionary directly, or you may assign .meta to a cell
        """
        return deepcopy(self._get_htf().get("meta"))

    @meta.setter
    def meta(self, value):
        from .assign import assign_connection
        parent = self._parent()
        assert parent is not None
        htf = self._get_htf()
        target_path = self._path + ("meta",)
        if isinstance(value, Cell):
            assert value._parent() is parent
            assign_connection(parent, value._path, target_path, False)
            htf.pop("meta", None)
        elif isinstance(value, Proxy):
            raise TypeError(".meta can only be assigned to a dict or to a whole Cell")
        else:
            if not isinstance(value, dict):
                raise TypeError(value)
            json.dumps(value)
            parent.remove_connections(target_path,endpoint="target")
            htf["meta"] = value
        self._get_htf()["UNTRANSLATED"] = True
        parent._translate()

    @property
    def RESULT(self):
        """The name of the result variable. Default is "result".

        This is also the attribute under which the result object is available
        (i.e. Transformer.result by default). The result object is similar
        to a (structured) Cell.
        """
        htf = self._get_htf()
        return htf["RESULT"]

    @RESULT.setter
    def RESULT(self, value):
        raise NotImplementedError
        htf = self._get_htf()
        result_path = self._path + (htf["RESULT"],)
        new_result_path = self._path + (value,)
        parent = self._parent()
        htf["RESULT"] = value

    @property
    def INPUT(self):
        """The name of the input attribute. Default is "inp".

        This is the attribute under which the input object is available
        (i.e. Transformer.inp by default). The input object is similar
        to a (structured) Cell.
        """
        htf = self._get_htf()
        return htf["INPUT"]

    @INPUT.setter
    def INPUT(self, value):
        raise NotImplementedError

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
    def scratch(self):
        """TODO: document"""
        htf = self._get_htf()
        return ("scratch" in htf)

    @scratch.setter
    def scratch(self, value):
        if value not in (True, False):
            raise TypeError(value)
        htf = self._get_htf()
        if value == True:
            htf["scratch"] = True
        else:
            htf.pop("scratch", None)

    def clear_exception(self):
        tf = self._get_tf(force=True)
        htf = self._get_htf()
        if htf["compiled"]:
            tf.tf.executor.clear_exception()
        else:
            tf.tf.clear_exception()

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
        self._get_htf()["UNTRANSLATED"] = True
        self._parent()._translate()

    @property
    def language(self):
        """Defines the programming language of the transformer's source code.

        Allowed values are: python, ipython, bash,
        or any compiled language.

        See seamless.compiler.languages and seamless.compile.compilers for a list
        """
        return self._get_htf()["language"]
    @language.setter
    def language(self, value):
        if value == "docker":
            import warnings
            warnings.warn(
                'Transformer.language="docker" is deprecated. Use language="bash" and set docker_image.',
                FutureWarning,
            )
            value = "bash"
        parent = self._parent()
        lang, language, extension = parent.environment.find_language(value)
        compiled = (language["mode"] == "compiled")
        htf = self._get_htf()
        old_language = htf.get("language")
        htf["language"] = lang
        old_compiled = htf.get("compiled", False)
        untranslate = False
        if old_compiled != compiled:
            htf["UNTRANSLATED"] = True
        elif (old_language == "bash" != (lang  == "bash")):
            htf["UNTRANSLATED"] = True
        htf["compiled"] = compiled
        htf["file_extension"] = extension
        has_translated = False
        if not has_translated:
            self._parent()._translate()

    @property
    def docker_image(self):
        """Defines the Docker image in which a transformer should run
        Getting this property is syntactic sugar for:
          Transformer.environment.get_docker()["name"]
        Setting this property is more-or-less syntactic sugar for:
          Transformer.environment.set_docker({"name": ...})
        """
        im = self.environment.get_docker()
        if im is None:
            return None
        return im["name"]

    @docker_image.setter
    def docker_image(self, docker):
        im = self.environment.get_docker()
        if im is None:
            im = {}
        im["name"] = docker
        self.environment.set_docker(im)

    @property
    def header(self):
        """For a compiled transformer, the generated C header"""
        htf = self._get_htf()
        assert htf["compiled"]
        dirs = ["value", "mount", "mimetype", "celltype"]
        return HeaderProxy(self, ("header",), "w", getter=self._header_getter, dirs=dirs)

    @header.setter
    def header(self, value):
        htf = self._get_htf()
        assert not htf["compiled"]
        return self._setattr("header", value)

    def _header_getter(self, attr):
        htf = self._get_htf()
        assert htf["compiled"]
        if attr == "celltype":
            return "code"
        elif attr == "value":
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
        """The schema of the transformer input object

        See Cell.schema for more details"""
        htf = self._get_htf()
        inp = htf["INPUT"]
        #TODO: self.self
        return getattr(self, inp).schema

    @property
    def example(self):
        """The example handle of the transformer input object.

        See Cell.example for more details
        """
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

    def add_validator(self, validator, name):
        """Adds a validator to the input, analogous to Cell.add_validator"""
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

    def __setitem__(self, item, value):
        if not isinstance(item, str):
            raise TypeError("item must be 'str', not '{}'".format(type(item)))
        return self._setattr(item, value)

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

        if not self._has_tf() and not isinstance(value, (Cell, Module)) and attr != htf["RESULT"]:
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
                get_form(value)
                htf["TEMP"]["input_auth"][attr] = value
                if attr not in htf["pins"]:
                    htf["pins"][attr] = default_pin.copy()
            parent = self._parent()
            parent.remove_connections(self._path + (attr,), endpoint="target")
            htf["UNTRANSLATED"] = True
            parent._translate()
            return

        if attr == "code":
            if isinstance(value, Resource):
                value = value.data
            if isinstance(value, Cell):
                target_path = self._path + (attr,)
                assert value._parent() is parent
                assign_connection(parent, value._path, target_path, False)
                translate = True
            elif isinstance(value, Proxy):
                raise AttributeError("".join(value._path))
            else:
                tf = self._get_tf(force=True)
                if callable(value):
                    value, _, _ = parse_function_code(value)
                check_libinstance_subcontext_binding(parent, self._path)
                removed = parent.remove_connections(self._path + (attr,), endpoint="target")
                if removed:
                    htf = self._get_htf()
                    htf["UNTRANSLATED"] = True
                    if "TEMP" not in htf or htf["TEMP"] is None:
                        htf["TEMP"] = {}
                    htf["TEMP"]["code"] = value
                    if "checksum" in htf:
                        htf["checksum"].pop("code", None)
                    translate = True
                else:
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
                removed = parent.remove_connections(self._path + (attr,), endpoint="target")
                if removed:
                    translate = True
                inp.handle_no_inference.set(value)
        elif attr == htf["RESULT"]:
            tf = self._get_tf(force=True)
            result = getattr(tf, htf["RESULT"])
            # Example-based programming to set the schema
            # TODO: suppress inchannel warning
            result.handle_no_inference.set(value)
        else:
            if attr not in htf["pins"]:
                if isinstance(value, Module):
                    pin = {
                        "celltype": "plain",
                        "subcelltype": "module",
                    }
                else:
                    pin = default_pin.copy()
                htf["pins"][attr] = pin
                translate = True
            if isinstance(value, (Cell, Module)):
                target_path = self._path + (attr,)
                assert value._parent() is parent
                assign_connection(parent, value._path, target_path, False)
                translate = True
            else:
                tf = self._get_tf(force=True)
                inp = getattr(tf, htf["INPUT"])
                removed = parent.remove_connections(self._path + (attr,), endpoint="target")
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
                p2 = getattr(p, subpath)
                if isinstance(p2, SynthContext) and p2._context is not None:
                    p2 = p2._context()
                p = p2

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
            p2 = getattr(p, subpath)
            if isinstance(p2, SynthContext) and p2._context is not None:
                p2 = p2._context()
            p = p2

        assert isinstance(p, CoreContext)
        return p

    def _get_htf(self):
        parent = self._parent()
        assert parent is not None
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


    def observe(self, attr, callback, polling_interval, observe_none=False):
        """Observes attributes of the result, analogous to Cell.observe"""
        if isinstance(attr, str):
            attr = (attr,)
        path = self._path + attr
        return self._get_top_parent().observe(
            path, callback, polling_interval,
            observe_none=observe_none
        )

    def unobserve(self, attr):
        """Analogous to Cell.unobserve"""
        if isinstance(attr, str):
            attr = (attr,)
        path = self._path + attr
        return self._get_top_parent().unobserve(path)

    @property
    def exception(self):
        """Returns the exception associated with the transformer.

        The exception may be raised during one of three stages:

        1. The construction of the input object (Transformer.inp).
           The input object is cell-like, see Cell.exception for more details.

        2. The execution of the transformer. For Python/IPython cells, this
           is the exception directly raised in code. For Bash/Docker cells,
           exceptions are raised upon non-zero exit codes.
           For compiled transformers, this stage is subdivided into
           generating the C header, compiling the code module, and executing
           the compiled code.

        3. The construction of the result object (Transformer.result).
           The result object is cell-like, see Cell.exception for more details.

        """
        htf = self._get_htf()
        if htf.get("UNTRANSLATED"):
            return "This transformer is untranslated; run 'ctx.translate()' or 'await ctx.translation()'"
        tf = self._get_tf(force=True).tf
        if htf["compiled"]:
            attrs = (
                htf["INPUT"], "code",
                "gen_header", "integrator", "executor",
                htf["RESULT"]
            )
        else:
            attrs = (
                htf["INPUT"], "code",
                "ipy_template_code", "apply_ipy_template", "ipy_code", "tf",
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
            elif k in ("ipy_template_code", "apply_ipy_template", "ipy_code"):
                tf2 = self._get_tf(force=True)
                try:
                    item = getattr(tf2, k)
                except AttributeError:                    
                    continue
                curr_exc = item.exception
            else:
                curr_exc = getattr(tf, k).exception
            if curr_exc is not None:
                if k == "executor":
                    if isinstance(curr_exc, dict) and list(curr_exc.keys()) == ["module"]:
                        curr_exc = curr_exc["module"]    
                if isinstance(curr_exc, dict):
                    curr_exc = pprint.pformat(curr_exc, width=100)
                exc += "*** " + k + " ***\n"
                exc += str(curr_exc)
                exc += "*** /" + k + " ***\n"
        if not len(exc):
            return None
        return exc

    @property
    def logs(self):
        """Returns the stdout/stderr logs of the transformer, if any"""
        htf = self._get_htf()
        if htf.get("UNTRANSLATED"):
            return None
        tf = self._get_tf(force=True).tf
        if htf["compiled"]:
            logs = ""
            for k in "gen_header", "integrator", "executor":
                subtf = getattr(tf, k)
                sublogs = subtf.logs
                if sublogs is not None and len(sublogs.strip()):
                    logs += "*** " + k + " ***\n"
                    logs += sublogs.strip() + "\n"
                    logs += "*** /" + k + " ***\n"    
            if not len(logs):
                return None
            return logs                
        else:
            return tf.logs

    @property
    def status(self):
        """The status of the transformer, analogous to Cell.status.

        See Transformer.exception about the different stages.
        The first stage with a non-OK status is reported."""

        htf = self._get_htf()
        if htf.get("UNTRANSLATED"):
            return "Status: error (ctx needs translation)"
        tf = self._get_tf(force=True).tf
        if htf["compiled"]:
            attrs = (
                htf["INPUT"], "code",
                "gen_header", "integrator", "executor",
                htf["RESULT"]
            )
        else:
            attrs = (
                htf["INPUT"], "code", 
                "ipy_template_code", "apply_ipy_template", "ipy_code", "tf",
                htf["RESULT"]
            )
        for k in attrs:
            pending = False
            upstream = False
            if k in (htf["INPUT"], htf["RESULT"]):
                if k == htf["INPUT"] and not len(htf["pins"]):
                    continue
                cell = getattr(self, k)
                status = cell.status
            elif k == "code":
                status = self._get_tf(force=True).code.status
            elif k == "tf":
                status = self._get_tf(force=True).tf.status
            elif k in ("ipy_template_code", "apply_ipy_template", "ipy_code"):
                tf2 = self._get_tf(force=True)
                try:
                    item = getattr(tf2, k)
                except AttributeError:                    
                    continue
                status = item.status
            else:
                tf = self._get_tf(force=True).tf
                status = getattr(tf, k).status
            if not status.endswith("OK"):
                if status.endswith(" pending"):
                    pending = True
                elif status.endswith(" upstream"):
                    upstream = True
                else:
                    return "*" + k + "*: " + status
        if upstream:
            return "Status: upstream"
        elif pending:
            return "Status: pending"
        return "Status: OK"

    @property
    def self(self):
        attributelist = [k for k in type(self).__dict__ if not k.startswith("_")]
        return SelfWrapper(self, attributelist)

    @property
    def link_options(self):
        """Linker options for compiled modules
        They are a list of strings, for example:
        ["-lm", "-lgfortran", "-lcudart"]
        """
        htf = self._get_htf()
        if not htf["compiled"]:
            raise AttributeError("Only for compiled transformers")
        return deepcopy(htf.get("link_options", []))

    @link_options.setter
    def link_options(self, link_options):
        htf = self._get_htf()
        if not htf["compiled"]:
            raise AttributeError("Only for compiled transformers")
        ok = True
        if not isinstance(link_options, list):
            ok = False
        else:
            for opt in link_options:
                if not isinstance(opt, str):
                    ok = False
        if not ok:
            raise TypeError("link_options must be a list of strings")
        htf["link_options"] = deepcopy(link_options)
        self._parent()._translate()

    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if attr in type(self).__dict__ or attr in self.__dict__ or attr == "path":
            return super().__getattribute__(attr)
        return self._getattr(attr)

    def __getitem__(self, item):
        if not isinstance(item, str):
            raise TypeError("item must be 'str', not '{}'".format(type(item)))
        return self._getattr(item)

    def _getattr(self, attr):
        htf = self._get_htf()
        dirs = None
        deleter = None
        setter = None
        pull_source = functools.partial(self._pull_source, attr)
        if attr in htf["pins"]:
            getter = functools.partial(self._valuegetter, attr)
            pin = getattr(self.pins, attr)
            setter = functools.partial(setattr, pin)
            dirs = ["value", "celltype", "subcelltype", "as_"]
            proxycls = Proxy
        elif attr == "pins":
            return PinsWrapper(self)
        elif attr == "code":
            getter = self._codegetter
            deleter = self._code_deleter
            dirs = ["value", "mount", "mimetype", "celltype"]
            proxycls = CodeProxy
        elif attr == htf["INPUT"]:
            getter = self._inputgetter
            dirs = [
              "value", "buffered", "data", "checksum",
              "schema", "example", "status", "exception",
              "add_validator", "handle"
            ] + list(htf["pins"].keys())
            setter = self._inputsetter
            return Proxy(
              self, (attr,), "w",
              pull_source=None, getter=getter, dirs=dirs,
              setter=setter,
              deleter=deleter
            )
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
        mode = "w" if setter is not None else "r"
        return proxycls(
            self, 
            (attr,), mode, 
            pull_source=pull_source, 
            getter=getter, setter=setter, dirs=dirs
        )

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

    def _sub_mount(self, attr, path=None, mode="rw", authority="file", persistent=True):
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
                    self._get_htf()["UNTRANSLATED"] = True
                    self._parent()._translate()
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
        self._get_htf()["UNTRANSLATED"] = True
        self._parent()._translate()

    def _codegetter(self, attr):
        if attr == "celltype":
            return "code"
        elif attr == "value":
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

    def _code_deleter(self, attr):
        if attr == "mount":
            htf = self._get_htf()
            if "mount" in htf:
                mount = htf["mount"]
                if "code" in mount:
                    mount.pop("code")
                    if not len(mount):
                        htf.pop("mount")
                    self._get_htf()["UNTRANSLATED"] = True
                    self._parent()._translate()
        else:
            raise AttributeError(attr)

    def _inputgetter(self, attr):
        htf = self._get_htf()
        if attr in htf["pins"]:
            return getattr(self, attr)
        if attr not in ("value", "status", "exception"):
            tf = self._get_tf(force=True)
            inputcell = getattr(tf, htf["INPUT"])
        if attr == "value":
            if htf.get("UNTRANSLATED"):
                return None
            tf = self._get_tf(force=True)
            inputcell = getattr(tf, htf["INPUT"])
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
            schema = inputcell.handle.schema
            return SchemaWrapper(self, schema, "SCHEMA")
        elif attr == "example":
            return self.example
        elif attr == "status":
            if htf.get("UNTRANSLATED"):
                return "This transformer is untranslated; run 'ctx.translate()' or 'await ctx.translation()'"
            tf = self._get_tf(force=True)
            inputcell = getattr(tf, htf["INPUT"])
            return inputcell._data.status # TODO; take into account validation, inchannel status
        elif attr == "exception":
            if htf.get("UNTRANSLATED"):
                return "Status: error (ctx needs translation)"
            tf = self._get_tf(force=True)
            inputcell = getattr(tf, htf["INPUT"])
            return inputcell.exception
        elif attr == "add_validator":
            handle = inputcell.handle_no_inference
            return handle.add_validator
        raise AttributeError(attr)

    def _inputsetter(self, attr, value):
        if attr in (
          "value", "data", "buffered",
          "checksum", "handle", "schema",
          "example", "status", "exception",
          "add_validator"
        ):
            raise AttributeError(attr)
        if isinstance(value, Cell):
            raise TypeError(value)
        htf = self._get_htf()
        if not self._has_tf():
            if isinstance(value, Resource):
                value = value.data
            if "TEMP" not in htf or htf["TEMP"] is None:
                htf["TEMP"] = {}
            if "input_auth" not in htf["TEMP"]:
                htf["TEMP"]["input_auth"] = {}
            get_form(value)
            htf["TEMP"]["input_auth"][attr] = value
            self._parent()._translate()
            return
        tf = self._get_tf(force=True)
        inputcell = getattr(tf, htf["INPUT"])
        handle = inputcell.handle_no_inference
        setattr(handle, attr, value)

    def _resultgetter(self, attr):
        htf = self._get_htf()
        if htf.get("UNTRANSLATED"):
            return None
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
            schema = self._result_example().schema
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
        if attr2 == "celltype":
            return getattr(self.pins, attr).celltype
        if attr2 == "subcelltype":
            return getattr(self.pins, attr).subcelltype
        if attr2 == "as_":
            return getattr(self.pins, attr).as_
        if attr2 != "value":
            raise AttributeError(attr2)
        return self._get_value(attr)

    def _pull_source(self, attr, path):
        from .assign import assign_connection
        tf = self._get_tf()
        htf = self._get_htf()
        parent = self._parent()
        def set_mount(node):
            if "mount" not in htf:
                return
            if htf["mount"].get("code") is None:
                return
            node["mount"] = htf["mount"].pop("code")
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
            set_mount(cell)
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
        child = Cell(parent=parent, path=path) #inserts itself as child
        parent._graph[0][path] = cell
        if "file_extension" in htf:
            child.mimetype = htf["file_extension"]
        else:
            mimetype = language_to_mime(language)
            child.mimetype = mimetype

        target_path = self._path + (attr,)
        assign_connection(parent, path, target_path, False)
        htf["UNTRANSLATED"] = True
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
            tf.main_module.auth._set_observer(self._observe_main_module)


    def __delattr__(self, attr):
        return delattr(self.pins, attr)
        # TODO: self.self.pins...

    def __dir__(self):
        htf = self._get_htf()
        d = super().__dir__()
        std = ["code", "pins", htf["RESULT"] , htf["INPUT"], "exception", "status"]
        if htf["compiled"]:
            std += list(("main_module", "header"))
        pins = list(htf["pins"].keys())
        return sorted(d + pins + std)

    def __str__(self):
        return "Seamless Transformer: " + self.path

    def __repr__(self):
        return str(self)

from .synth_context import SynthContext
from .assign import check_libinstance_subcontext_binding