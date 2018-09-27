import weakref
import inspect
from types import LambdaType
from .Base import Base
from ..midlevel import TRANSLATION_PREFIX
from ..core.lambdacode import lambdacode
from ..silk import Silk
from .mime import get_mime, language_to_mime, ext_to_mime

class Cell(Base):
    _virtual_path = None

    def __init__(self, parent=None, path=None):
        assert (parent is None) == (path is None)
        if parent is not None:
            self._init(parent, path)

    def _init(self, parent, path):
        super().__init__(parent, path)
        parent._children[path] = self

    @property
    def authoritative(self):
        #TODO: determine if the cell didn't get any inbound connections
        # If it did, you can't get another inbound connection, nor a link
        return True #stub

    @property
    def links(self):
        #TODO: return the other partner of all Link objects with self in it
        return [] #stub

    def __str__(self):
        try:
            return str(self._get_cell())
        except AttributeError:
            raise
            return("Cell %s in dummy mode" % ("." + ".".join(self._path)))

    def _get_cell(self):
        parent = self._parent()
        if parent._dummy:
            raise AttributeError
        if not parent._translating:
            parent.translate()
        p = getattr(parent._ctx, TRANSLATION_PREFIX)
        for subpath in self._path:
            p = getattr(p, subpath)
        return p

    def _get_hcell(self):
        parent = self._parent()
        return parent._graph.nodes[self._path]

    def self(self):
        raise NotImplementedError

    def __getattr__(self, attr):
        if attr == "value":
            raise AttributeError(attr) #property has failed
        if attr == "schema":
            hcell = self._get_hcell()
            if hcell["celltype"] == "structured":
                cell = self._get_cell()
                return cell.handle.schema
            else:
                raise AttributeError
        hcell = self._get_hcell()
        if not hcell["celltype"] == "structured":
            cell = self._get_cell()
            return getattr(cell, attr)
        parent = self._parent()
        readonly = not test_lib_lowlevel(parent, self._get_cell())
        return SubCell(self._parent(), self, (attr,), readonly=readonly)

    def mount(self, path=None, mode="rw", authority="cell", persistent=True):
        hcell = self._get_hcell()
        mount = {
            "path": path,
            "mode": mode,
            "authority": authority,
            "persistent": persistent
        }
        hcell["mount"] = mount
        #self._parent().translate(force=True)

    def __setattr__(self, attr, value):
        if attr.startswith("_") or hasattr(type(self), attr):
            return object.__setattr__(self, attr, value)
        from .assign import assign_to_subcell
        parent = self._parent()
        assert not parent._dummy
        assert not test_lib_lowlevel(parent, self._get_cell())
        subcell = getattr(self, attr)
        #TODO: break links and connections from subcell
        assign_to_subcell(self, (attr,), value)
        ctx = parent._ctx
        if parent._as_lib is not None:
            hcell = self._get_hcell()
            if hcell["path"] in parent._as_lib.partial_authority:
                parent._as_lib.needs_update = True
        parent._translate()

    @property
    def value(self):
        parent = self._parent()
        hcell = self._get_hcell()
        if parent._dummy:
            if hcell["celltype"] == "structured":
                state = hcell.get("stored_state", None)
                if state is None:
                    state = hcell.get("cached_state", None)
                value = None
                if state is not None:
                    if hcell["silk"]:
                        value = Silk(data=state.data, schema=state.schema)
                    else:
                        value = state.data
            else:
                value = hcell.get("stored_value", None)
                if value is None:
                    value = hcell.get("cached_value", None)
            return value
        else:
            try:
                cell = self._get_cell()
            except:
                import traceback; traceback.print_exc()
                raise
            value = cell.value
            ###if hcell["celltype"] == "structured":
            ###    value = value.value
            return value

    @property
    def handle(self):
        cell = self._get_cell()
        return cell.handle

    @property
    def data(self):
        cell = self._get_cell()
        return cell.data

    def _set(self, value):
        #TODO: check if sovereign cell => disable warning!!
        from . import set_hcell
        from ..silk import Silk
        hcell = self._get_hcell()
        if "TEMP" in hcell:
            hcell["TEMP"] = value
            return
        try:
            cell = self._get_cell()
            cell.set(value)
            value = cell.value
        except AttributeError: #not yet been translated
            if callable(value) and not isinstance(value, Silk):
                code = inspect.getsource(value)
                if isinstance(value, LambdaType) and func.__name__ == "<lambda>":
                    code = lambdacode(value)
                    if code is None:
                        raise ValueError("Cannot extract source code from this lambda")
                value = code
        set_hcell(hcell, value)

    def set(self, value):
        self._set(value)

    def __add__(self, other):
        self.set(self.value + other)

    @property
    def celltype(self):
        hcell = self._get_hcell()
        return hcell["celltype"]

    @celltype.setter
    def celltype(self, value):
        assert value in ("structured", "text", "code", "json", "mixed", "array", "signal"), value
        hcell = self._get_hcell()
        if "TEMP" in hcell:
            cellvalue = hcell["TEMP"]
        else:
            cellvalue = self.value
        hcell["celltype"] = value
        if cellvalue is not None and "TEMP" not in hcell:
            self._parent().translate(force=True) # This needs to be kept!
            self.set(cellvalue)
        else:
            self._parent()._translate()
        self._update_dep()

    @property
    def mimetype(self):
        hcell = self._get_hcell()
        mimetype = hcell.get("mimetype")
        if mimetype is not None:
            return mimetype
        celltype = hcell["celltype"]
        if celltype == "code":
            language = hcell["language"]
            mimetype = language_to_mime(language)
            return mimetype
        if celltype == "structured":
            datatype = hcell["datatype"]
            if datatype in ("mixed", "binary"):
                mimetype = get_mime(datatype)
            else:
                mimetype = ext_to_mime(datatype)
        else:
            mimetype = get_mime(celltype)
        return mimetype

    @mimetype.setter
    def mimetype(self, value):
        if value.find("/") == -1:
            try:
                value = ext_to_mime(value)
            except KeyError:
                raise ValueError("Unknown extension %s" % value) from None
        hcell = self._get_hcell()
        hcell["mimetype"] = value

    @property
    def datatype(self):
        hcell = self._get_hcell()
        celltype = hcell["celltype"]
        assert celltype == "structured"
        return hcell["datatype"]

    @datatype.setter
    def datatype(self, value):
        hcell = self._get_hcell()
        celltype = hcell["celltype"]
        assert celltype == "structured"
        hcell["datatype"] = value

    def _update_dep(self):
        self._parent()._depsgraph.update_path(self._path)

from .Library import test_lib_lowlevel
from .SubCell import SubCell
