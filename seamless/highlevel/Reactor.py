import weakref
import functools
from copy import deepcopy
from .Cell import Cell
from .Resource import Resource
from .proxy import Proxy, CodeProxy
from .pin import InputPin, OutputPin
from .Base import Base
from .Library import test_lib_lowlevel
from .mime import language_to_mime
from ..core.context import Context as CoreContext

class Reactor(Base):
    def __init__(self, parent=None, path=None):
        assert (parent is None) == (path is None)
        if parent is not None:
            self._init(parent, path)

    def _init(self, parent, path):
        super().__init__(parent, path)
        parent._children[path] = self
        hrc = {
            "path": path,
            "type": "reactor",
            "language": "python",
            #"code_start": None,
            #"code_update": None,
            #"code_stop": None,
            "pins": {},
            "IO": "io",
            "buffered": True,
            "plain": False,
            "UNTRANSLATED": True
        }
        parent._graph.nodes[path] = hrc

    def set_pin(self, pinname, *,
        io=None,
        transfer_mode=None,
        access_mode=None,
        content_type=None,
        must_be_defined=None
      ): #docstring copied from .core.protocol.protocol.py
        """Define a new pin, or update an existing one
- pin: name of the pin
- io: the type of the pin. Can be "input", "output" or "edit".
  Only pins declare this.
- transfer mode: this declares how the data is transferred.
  - "buffer": the data is transferred as a buffer that can be directly written
    to/from file. It depends on the content type whether the file should be opened
    in text or in binary mode.
  - "copy": the data is transferred as a deep copy that is safe against modifications
    (however, only for edit pins such modifications would be appropriate)
  - "ref": the data is transferred as a reference that should not be modified.
    "ref" merely indicates that a copy is not necessary.
    If transfer-by-reference is not possible for any reason, a copy is transferred instead.
  - "signal": the connection is a signal, no data whatsoever is transferred
- access mode: this declares in which form the data will be accessible to the recipient
  - object: generic Python object (only with "object", "binary" or "mixed" content type)
    Also the format of set_cell
  - pythoncode: a string that can be exec'ed by Python
  - json: the result of json.load, i.e. nested dicts, lists and basic types (str/float/int/bool).
  - silk: a Silk object
  - text: a text string
  - module: a Python module
- content type: the semantic content of the data
  - object: generic Python object
  - text: text
  - python: generic python code
  - ipython: IPython code
  - transformer: transformer code
  - reactor: reactor code
  - macro: macro code
  - json: JSON data
  - cson: CSON data
  - mixed: seamless.mixed data
  - binary: Numpy data"""
        #TODO: validation
        hrc = self._get_hrc()
        # also, in case of output/edit, assert that there is no existing inbound connection
        if pinname not in hrc["pins"]:
            assert io is not None #must be defined for a new pin
            hrc["pins"][pinname] = {}
            transfer_mode = "copy" if transfer_mode is None else transfer_mode
            access_mode = "silk" if access_mode is None else access_mode
        pin = {}
        if io is not None:
            pin["io"] = io
        if transfer_mode is not None:
            pin["transfer_mode"] = transfer_mode
        if access_mode is not None:
            pin["access_mode"] = access_mode
        if content_type is not None:
            pin["content_type"] = content_type
        if must_be_defined is not None:
            pin["must_be_defined"] = must_be_defined
        hrc["pins"][pinname].update(pin)
        self._parent()._translate()

    @property
    def pins(self):
        hrc = self._get_hrc()
        return deepcopy(hrc["pins"])

    def delete_pin(self, pin):
        hrc = self._get_hrc()
        hrc["pins"].pop(pin, None)

    def __setattr__(self, attr, value):
        from .assign import assign_connection
        from ..midlevel.copying import fill_structured_cell_value
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        translate = False
        parent = self._parent()
        hrc = self._get_hrc()

        if isinstance(value, Resource):
            assert attr in ("code_start", "code_update", "code_stop")
            if "mount" not in hrc:
                hrc["mount"] = {}
            mount = {
                "path": value.filename,
                "mode": "r",
                "authority": "file",
                "persistent": True,
            }
            hrc["mount"][attr] = mount
            translate = True

        if not self._has_rc() and not isinstance(value, Cell):
            if isinstance(value, Resource):
                value = value.data
            if "TEMP" not in hrc or hrc["TEMP"] is None:
                hrc["TEMP"] = {}
            hrc["TEMP"][attr] = value
            self._parent()._translate()
            return

        if attr in ("code_start", "code_update", "code_stop"):
            rc = self._get_rc()
            cell = getattr(rc, attr)
            assert not test_lib_lowlevel(parent, cell)
            if isinstance(value, Resource):
                hrc[attr] = value.data
            else:
                cell.set(value)
                hrc[attr] = cell.value
        else:
            if attr not in hrc["pins"]:
                hrc["pins"][attr] = {"io": "input", "transfer_mode": "copy", "access_mode": "silk"}
                translate = True
            if isinstance(value, Cell):
                ###io = getattr(rc, hrc["IO"])
                ###assert not test_lib_lowlevel(parent, io) #TODO: test this at hrc level, not rc
                target_path = self._path + (attr,)
                assert value._parent() == parent
                #TODO: check existing inchannel connections and links (cannot be the same or higher)
                assign_connection(parent, value._path, target_path, False)
                translate = True
            else:
                rc = self._get_rc()
                io = getattr(rc, hrc["IO"])
                assert not test_lib_lowlevel(parent, io) #TODO: test this at hrc level, not rc
                if parent._needs_translation:
                    translate = False #_get_rc() will translate
                rc = self._get_rc()
                io = getattr(rc, hrc["IO"])
                setattr(io.handle, attr, value)
        if parent._as_lib is not None:
            parent._as_lib.needs_update = True
        if translate:
            parent._translate()


    def _get_value(self, attr):
        rc = self._get_rc()
        hrc = self._get_hrc()
        if attr in ("code_start", "code_update", "code_stop"):
            p = getattr(rc, attr)
            return p.data
        else:
            io = getattr(rc, hrc["IO"])
            p = io.value[attr]
            return p

    def __getattr__(self, attr):
        if attr.startswith("_"):
            raise AttributeError(attr)
        hrc = self._get_hrc()
        if attr == hrc["IO"]:
            # TODO: better wrapping
            return getattr(self._get_rc(), hrc["IO"])
        if attr not in hrc["pins"] and \
          attr not in ("code_start", "code_update", "code_stop"):
            #TODO: could be result pin... what to do?
            raise AttributeError(attr)
        pull_source = functools.partial(self._pull_source, attr)
        if attr in ("code_start", "code_update", "code_stop"):
            getter = functools.partial(self._codegetter, attr)
            proxycls = CodeProxy
        else:
            getter = functools.partial(self._valuegetter, attr)
            proxycls = Proxy
        return proxycls(self, (attr,), "r", pull_source=pull_source, getter=getter)

    def _codegetter(self, attr, attr2):
        if attr2 == "value":
            rc = self._get_rc()
            return getattr(rc, attr).value
        elif attr2 == "mimetype":
            hrc = self._get_hrc()
            language = hrc["language"]
            mimetype = language_to_mime(language)
            return mimetype
        else:
            raise AttributeError(attr2)

    def _valuegetter(self, attr, attr2):
        if attr2 != "value":
            raise AttributeError(attr2)
        return self._get_value(attr)

    def _pull_source(self, attr, other):
        from .assign import assign_connection
        rc = self._get_rc()
        hrc = self._get_hrc()
        parent = self._parent()
        assert other._parent() is parent
        path = other._path
        if attr in ("code_start", "code_update", "code_stop"):
            p = getattr(rc, attr)
            value = p.data
            cell = {
                "path": path,
                "type": "cell",
                "celltype": "code",
                "language": "python",
                "transformer": False,
            }
            if value is not None:
                assert isinstance(value, str)
                cell["TEMP"] = value
            hrc[attr] = None
        else:
            io = getattr(rc, hrc["IO"])
            p = getattr(io.value, attr)
            value = p.value
            cell = {
                "path": path,
                "type": "cell",
                "celltype": "structured",
                "datatype": "mixed",
                "silk": True,
                "buffered": True,
            }
        #TODO: check existing inchannel connections and links (cannot be the same or higher)
        child = Cell(parent, path) #inserts itself as child
        parent._graph[0][path] = cell
        target_path = self._path + (attr,)
        assign_connection(parent, other._path, target_path, False)
        child.set(value)
        parent._translate()


    def _has_rc(self):
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

    def _get_rc(self, may_translate=True):
        parent = self._parent()
        if may_translate and not parent._translating:
            parent._do_translate()
        else:
            if not self._has_rc():
                return None
        p = parent._gen_context
        for subpath in self._path:
            p = getattr(p, subpath)
        assert isinstance(p, CoreContext)
        return p

    def status(self):
        return self._get_rc().status()

    def _get_hrc(self):
        parent = self._parent()
        return parent._graph[0][self._path]

    def __delattr__(self, attr):
        hrc = self._get_hrc()
        raise NotImplementedError #remove pin
