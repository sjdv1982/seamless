import weakref
import inspect
import traceback
import threading
from types import LambdaType
from .Base import Base
from .Resource import Resource
from ..core.lambdacode import lambdacode
from ..silk import Silk
from ..mixed import MixedBase
from .mime import get_mime, language_to_mime, ext_to_mime

celltypes = (
    "structured", "text", "code", "plain", "mixed", "binary",
    "cson", "yaml", "str", "bytes", "int", "float", "bool"
)    

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
        parent = self._parent()
        connections = parent._graph.connections
        path = self._path
        lp = len(path)
        for con in connections:
            if con["type"] == "connection":
                if con["target"][:lp] == path:
                    return False
        return True

    def get_links(self):        
        result = []
        path = self._path()
        lp = len(path)
        for link in self._parent().get_links():
            if link._node["first"][:lp] == path:
                result.append(link)
            elif link._node["second"][:lp] == path:
                result.append(link)
        return result

    def __rshift__(self, other):
        from .proxy import Proxy
        proxy = Proxy(self._parent(), "w")        
        assert isinstance(other, Proxy)
        assert "r" in other._mode
        assert other._pull_source is not None
        other._pull_source(proxy)

    def __str__(self):
        return str(self._get_cell())
        """
        try:
            return str(self._get_cell())
        except AttributeError:
            return("Cell %s in dummy mode" % ("." + ".".join(self._path)))
        """

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
            pp = self._path[0]
            p = getattr(p, pp)
        return self._get_cell_subpath(p, self._path[1:])

    def _get_hcell(self):
        parent = self._parent()
        return parent._get_node(self._path)

    def _observe_cell(self, checksum):
        if self._parent() is None:
            return
        hcell = self._get_hcell()
        if hcell.get("checksum") is None:
            hcell["checksum"] = {}
        hcell["checksum"].pop("value", None)
        if checksum is not None:
            hcell["checksum"]["value"] = checksum

    def _observe_auth(self, checksum):
        if self._parent() is None:
            return
        hcell = self._get_hcell()
        if hcell.get("checksum") is None:
            hcell["checksum"] = {}
        hcell["checksum"].pop("auth", None)
        if checksum is not None:
            hcell["checksum"]["auth"] = checksum

    def _observe_buffer(self, checksum):
        if self._parent() is None:
            return
        hcell = self._get_hcell()
        if hcell.get("checksum") is None:
            hcell["checksum"] = {}
        hcell["checksum"].pop("buffer", None)
        if checksum is not None:
            hcell["checksum"]["buffer"] = checksum

    def _observe_schema(self, checksum):
        if self._parent() is None:
            return
        hcell = self._get_hcell()
        if hcell.get("checksum") is None:
            hcell["checksum"] = {}
        hcell["checksum"].pop("schema", None)
        if checksum is not None:
            hcell["checksum"]["schema"] = checksum

    def self(self):
        raise NotImplementedError

    def __getitem__(self, item):
        if isinstance(item, (int, str)):
            hcell = self._get_hcell()
            if not hcell["celltype"] == "structured":
                raise AttributeError(item)
            parent = self._parent()
            readonly = False ### TODO
            return SubCell(self._parent(), self, (item,), readonly=readonly)
        elif isinstance(item, slice):
            raise NotImplementedError  # TODO: x[min:max] outchannels
        else:
            raise TypeError(item)

    def __getattr__(self, attr):
        if attr in (
            "value", "example", "status", 
            "authoritative", "checksum", "handle", "data", 
            "celltype", "mimetype", "datatype",
            "hash_pattern", "language"
        ):
            raise AttributeError(attr) #property has failed
        if attr == "schema":
            hcell = self._get_hcell()
            if hcell["celltype"] == "structured":
                cell = self._get_cell()
                schema = cell.get_schema()
                return SchemaWrapper(self, schema, "SCHEMA")
            else:
                raise AttributeError
        hcell = self._get_hcell()
        if not hcell["celltype"] == "structured":
            cell = self._get_cell()
            return getattr(cell, attr)
        parent = self._parent()
        readonly = False ### TODO
        return SubCell(self._parent(), self, (attr,), readonly=readonly)

    def mount(self, path=None, mode="rw", authority="cell", persistent=True):
        assert self.celltype != "structured"
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
        if attr == "example":
            return getattr(self, "example").set(value)
        if attr.startswith("_") or hasattr(type(self), attr):
            return object.__setattr__(self, attr, value)
        return self._setattr(attr, value)

    def _setattr(self, attr, value):
        from .assign import assign_to_subcell
        parent = self._parent()
        assert not parent._dummy

        if isinstance(value, Resource):
            value = value.data
        elif isinstance(value, Proxy):
            # TODO: implement for Transformer "code", "value", "schema", "example"
            raise NotImplementedError(value)

        hcell = self._get_hcell()
        if hcell.get("UNTRANSLATED"):
            self._parent().translate(force=True)
            return self._setattr(attr, value)

        assign_to_subcell(self, (attr,), value)

    def __setitem__(self, item, value):
        if item in ("value", "schema"):
            raise NotImplementedError # TODO: might work on shadowed inchannels, but probably need to adapt assign_to_subcell
        if isinstance(item, str) and item.startswith("_"):
            raise NotImplementedError # TODO: might work on shadowed inchannels, but need to adapt __setattr__

        if isinstance(item, str):
            return setattr(self, item, value)
        elif isinstance(item, int):
            raise NotImplementedError # TODO: should work, but need to adapt __setattr__
        elif isinstance(item, slice):
            raise NotImplementedError  # TODO: x[min:max] inchannels
        else:
            raise TypeError(item)


    def traitlet(self, fresh=False):
        return self._parent()._add_traitlet(self._path, None, fresh)

    @property
    def value(self):
        parent = self._parent()
        hcell = self._get_hcell()
        if parent._dummy:
            raise NotImplementedError
        if hcell.get("UNTRANSLATED") and "TEMP" in hcell:
            #return hcell["TEMP"]
            raise Exception # value untranslated; translation is async!
        try:
            cell = self._get_cell()
        except Exception:
            import traceback; traceback.print_exc()
            raise
        value = cell.value
        return value

    @property
    def example(self):        
        if self.celltype != "structured":
            raise AttributeError
        cell = self._get_cell()
        struc_ctx = cell._data._context()
        return struc_ctx.example.handle

    def add_validator(self, validator):
        return self.handle.add_validator(validator)

    @property
    def exception(self):        
        if self.celltype != "structured":
            raise AttributeError
        cell = self._get_cell()
        return cell.exception

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
            except Exception:
                import traceback; traceback.print_exc()
                raise
            return cell.checksum

    @checksum.setter
    def checksum(self, checksum):
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
        return cell.handle_no_inference

    @property
    def data(self):
        cell = self._get_cell()
        return cell.data

    def _set(self, value):
        from ..core.structured_cell import StructuredCell
        hcell = self._get_hcell()
        if hcell.get("UNTRANSLATED"):
            hcell["TEMP"] = value
            return
        cell = self._get_cell()
        if isinstance(cell, StructuredCell):
            cell.set_no_inference(value)
        else:
            cell.set(value)

    @property
    def status(self):
        cell = self._get_cell()
        return cell.status

    def set(self, value):
        self._set(value)

    @property
    def celltype(self):
        hcell = self._get_hcell()
        return hcell["celltype"]

    @celltype.setter
    def celltype(self, value):
        assert value in celltypes, value
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
        if value in ("structured", "mixed"):
            if "hash_pattern" not in hcell:
                hcell["hash_pattern"] = None
        else:
            hcell.pop("hash_pattern", None)
        if value == "code" and "language" not in hcell:
            hcell["language"] = "python"
        hcell.pop("checksum", None)
        if cellvalue is not None and not hcell.get("UNTRANSLATED"):
            self._parent()._do_translate(force=True) # This needs to be kept!
            self.set(cellvalue)
        else:
            self._parent()._translate()

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

    @property
    def hash_pattern(self):
        hcell = self._get_hcell()
        celltype = hcell["celltype"]
        assert celltype in ("structured", "mixed")
        return hcell["hash_pattern"]

    @hash_pattern.setter
    def hash_pattern(self, value):
        from ..core.protocol.deep_structure import validate_hash_pattern
        validate_hash_pattern(value)
        hcell = self._get_hcell()
        celltype = hcell["celltype"]
        assert celltype in ("structured", "mixed")
        hcell["hash_pattern"] = value
        hcell.pop("checksum", None)
        self._parent()._translate()

    @property
    def language(self):
        hcell = self._get_hcell()
        celltype = hcell["celltype"]
        if celltype != "code":
            raise AttributeError

    @language.setter
    def language(self, value):
        from ..compiler import find_language
        hcell = self._get_hcell()
        celltype = hcell["celltype"]
        if celltype != "code":
            return self._setattr("language", value)
        lang, language, extension = find_language(value)
        old_language = hcell.get("language")
        hcell["language"] = lang
        hcell["file_extension"] = extension
        self._parent()._translate()

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
            except Exception:
                pass
        return result
    
    def _set_observers(self):
        from ..core.cell import Cell as CoreCell
        from ..core.structured_cell import StructuredCell
        cell = self._get_cell()
        if not isinstance(cell, (CoreCell, StructuredCell)):
            raise Exception(cell)        
        if self.celltype == "structured":
            if cell.auth is not None:
                cell.auth._set_observer(self._observe_auth)
            cell._data._set_observer(self._observe_cell)
            cell.buffer._set_observer(self._observe_buffer)
            if cell.schema is not None:
                cell.schema._set_observer(self._observe_schema)            
        else:
            cell._set_observer(self._observe_cell)        

    def __str__(self):
        return "Seamless Cell: %s" % ".".join(self._path)

def cell_binary_method(self, other, name):
    h = self.handle 
    method = getattr(h, name)
    if method is NotImplemented:
        return NotImplemented
    return method(other)
 

def Constant(*args, **kwargs):
    cell = Cell(*args, **kwargs)
    cell._get_hcell()["constant"] = True 

from functools import partialmethod
from ..silk.SilkBase import binary_special_method_names
for name in binary_special_method_names:
    if name in Cell.__dict__:
        continue
    m = partialmethod(cell_binary_method, name=name)
    setattr(Cell, name, m)

from .SubCell import SubCell
from .SchemaWrapper import SchemaWrapper
from .proxy import Proxy
from ..midlevel.util import STRUC_ID