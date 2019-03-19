import weakref
import inspect
import traceback
import threading
from types import LambdaType
from .Base import Base
from ..core.lambdacode import lambdacode
from ..silk import Silk
from ..mixed import MixedBase
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

    def _get_cell_subpath(self, cell, subpath):
        p = cell
        for path in subpath:
            p = getattr(p, path)
        return p

    def _get_cell(self):
        parent = self._parent()
        if parent._dummy:
            raise AttributeError
        if not parent._translating:
            if threading.current_thread() == threading.main_thread():
                parent._do_translate()
        p = parent._gen_context
        if len(self._path):
            p = getattr(p, self._path[0])
        return self._get_cell_subpath(p, self._path[1:])

    def _get_hcell(self):
        parent = self._parent()
        return parent._graph.nodes[self._path]

    def _set_checksum(self, checksum):
        hcell = self._get_hcell()
        hcell["checksum"] = checksum

    def self(self):
        raise NotImplementedError

    def __getitem__(self, item):
        if isinstance(item, int):
            raise NotImplementedError  # TODO: x[int] outchannels
        if isinstance(item, str):
            raise NotImplementedError  # TODO: x[attr] as alternative for x.attr
        elif isinstance(item, slice):
            raise NotImplementedError  # TODO: x[min:max] outchannels
        else:
            raise TypeError(item)

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
        if path is None:
            hcell.pop("mount", None)
        else:
            mount = {
                "path": path,
                "mode": mode,
                "authority": authority,
                "persistent": persistent
            }
            hcell["mount"] = mount
        self._parent()._translate()

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
        ctx = parent._gen_context
        if parent._as_lib is not None:
            hcell = self._get_hcell()
            if hcell["path"] in parent._as_lib.partial_authority:
                parent._as_lib.needs_update = True
        parent._translate()

    def traitlet(self, fresh=False):
        return self._parent()._add_traitlet(self._path, None, fresh)

    @property
    def value(self):
        parent = self._parent()
        hcell = self._get_hcell()
        if parent._dummy:
            raise NotImplementedError
        elif hcell.get("UNTRANSLATED"):
            return hcell.get("TEMP")
        else:
            try:
                cell = self._get_cell()
            except:
                import traceback; traceback.print_exc()
                raise
            value = cell.value
            return value

    @property
    def checksum(self):
        parent = self._parent()
        hcell = self._get_hcell()
        if parent._dummy:
            raise NotImplementedError
        elif hcell.get("UNTRANSLATED"):
            if "TEMP" in hcell:
                cell = self._get_cell()
                return cell.checksum
            return hcell.get("checksum")
        else:
            try:
                cell = self._get_cell()
            except:
                import traceback; traceback.print_exc()
                raise
            return cell.checksum

    @checksum.setter
    def checksum(self, checksum):
        from . import set_hcell
        from ..silk import Silk
        hcell = self._get_hcell()
        if hcell.get("UNTRANSLATED"):
            hcell["checksum"] = checksum
            return
        cell = self._get_cell()
        cell.set_checksum(checksum)

    @property
    def handle(self):
        cell = self._get_cell()
        return cell.handle

    @property
    def data(self):
        cell = self._get_cell()
        return cell.data

    def _set(self, value):
        from . import set_hcell
        from ..silk import Silk
        hcell = self._get_hcell()
        if hcell.get("UNTRANSLATED"):
            hcell["TEMP"] = value
            return
        cell = self._get_cell()
        cell.set(value)

    @property
    def status(self):
        cell = self._get_cell()
        return cell.status

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
        if hcell.get("UNTRANSLATED"):
            cellvalue = hcell.get("TEMP")
        else:
            cellvalue = self.value
        if isinstance(cellvalue, Silk):
            cellvalue = cellvalue.data
        if isinstance(cellvalue, MixedBase):
            cellvalue = cellvalue.value
        hcell["celltype"] = value
        if cellvalue is not None and not hcell.get("UNTRANSLATED"):
            self._parent()._do_translate(force=True) # This needs to be kept!
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
        hcell = self._get_hcell()
        if value.find("/") == -1:
            try:
                ext = value
                value = ext_to_mime(ext)
            except KeyError:
                raise ValueError("Unknown extension %s" % ext) from None
            hcell["file_extension"] = ext
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

    def __rshift__(self, other):
        assert isinstance(other, Proxy)
        assert "r" in other._mode
        assert other._pull_source is not None
        other._pull_source(self)

    def share(self):
        self._parent()._share(self)

    def __dir__(self):
        result = super().__dir__()
        parent = self._parent()
        hcell = self._get_hcell()
        if not parent._dummy:
            try:
                celltype = hcell["celltype"]
                if celltype == "structured" and hcell["silk"]:
                    result += dir(self.value)
            except:
                pass
        return result


from .Library import test_lib_lowlevel
from .SubCell import SubCell
from .proxy import Proxy
