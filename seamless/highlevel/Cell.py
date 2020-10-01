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
from ..mime import get_mime, language_to_mime, ext_to_mime

celltypes = (
    "structured", "text", "code", "plain", "mixed", "binary",
    "cson", "yaml", "str", "bytes", "int", "float", "bool",
    "checksum"
)

def get_new_cell(path):
    return {
        "path": path,
        "type": "cell",
        "celltype": "structured",
        "datatype": "mixed",
        "hash_pattern": None,
        "UNTRANSLATED": True,
    }

class Cell(Base):
    """Cell class. Contains a piece of data in Seamless.

    See http://sjdv1982.github.io/seamless/sphinx/html/cell.html for documentation
    """

    _virtual_path = None
    _node = None
    _subpath = ()

    def __init__(self, celltype=None, *, parent=None, path=None):
        assert (parent is None) == (path is None)
        if parent is not None:
            self._init(parent, path)
        if celltype is not None:
            self.celltype = celltype

    def _init(self, parent, path):
        super().__init__(parent=parent, path=path)
        parent._children[path] = self

    @property
    def authoritative(self):
        """True if the cell has no dependencies"""
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
        path = self._path
        lp = len(path)
        for link in self._parent().get_links():
            if link._node["first"][:lp] == path:
                result.append(link)
            elif link._node["second"][:lp] == path:
                result.append(link)
        return result

    def _get_cell_subpath(self, cell, subpath):
        p = cell
        for path in subpath:
            p2 = getattr(p, path)
            if isinstance(p2, SynthContext) and p2._context is not None:
                p2 = p2._context()
            p = p2
        return p

    def _get_cell(self):
        ###hcell = self._get_hcell() # infinite loop...
        ###assert not hcell.get("UNTRANSLATED")
        parent = self._parent()
        p = parent._gen_context
        if p is None:
            raise ValueError
        if len(self._path):
            pp = self._path[0]
            p2 = getattr(p, pp)
            if isinstance(p2, SynthContext) and p2._context is not None:
                p2 = p2._context()
            p = p2
        return self._get_cell_subpath(p, self._path[1:])

    def _get_hcell(self):
        parent = self._parent()
        return parent._get_node(self._path)

    def _get_hcell2(self):
        try:
            return self._get_hcell()
        except AttributeError:
            pass
        if self._node is None:
            self._node = get_new_cell(None)
        return self._node

    def _observe_cell(self, checksum):
        if self._parent() is None:
            return
        if self._parent()._translating:
            return
        try:
            hcell = self._get_hcell()
        except Exception:
            return
        if hcell.get("UNTRANSLATED"):
            print("WARNING: ignored value update for %s, because celltype changed" % self)
            return
        if hcell.get("checksum") is None:
            hcell["checksum"] = {}
        hcell["checksum"].pop("value", None)
        if checksum is not None:
            hcell["checksum"]["value"] = checksum

    def _observe_auth(self, checksum):
        if self._parent() is None:
            return
        if self._parent()._translating:
            return
        try:
            hcell = self._get_hcell()
        except Exception:
            return
        if hcell.get("UNTRANSLATED"):
            print("WARNING: ignored value update for %s, because celltype changed" % self)
            return
        if hcell.get("checksum") is None:
            hcell["checksum"] = {}
        hcell["checksum"].pop("auth", None)
        if checksum is not None:
            hcell["checksum"]["auth"] = checksum

    def _observe_buffer(self, checksum):
        if self._parent() is None:
            return
        if self._parent()._translating:
            return
        try:
            hcell = self._get_hcell()
        except Exception:
            return
        if hcell.get("UNTRANSLATED"):
            print("WARNING: ignored value update for %s, because celltype changed" % self)
            return
        if hcell.get("checksum") is None:
            hcell["checksum"] = {}
        hcell["checksum"].pop("buffer", None)
        if checksum is not None:
            hcell["checksum"]["buffer"] = checksum

    def _observe_schema(self, checksum):
        if self._parent() is None:
            return
        if self._parent()._translating:
            return
        try:
            hcell = self._get_hcell()
        except Exception:
            return
        if hcell.get("checksum") is None:
            hcell["checksum"] = {}
        hcell["checksum"].pop("schema", None)
        if checksum is not None:
            hcell["checksum"]["schema"] = checksum

    def _cell(self):
        return self

    def self(self):
        raise NotImplementedError

    def _get_subcell(self, attr):
        hcell = self._get_hcell()
        if not hcell["celltype"] == "structured":
            raise AttributeError(item)
        parent = self._parent()
        readonly = False ### TODO
        path = self._subpath + (attr,)
        return SubCell(
            parent, self._cell(),
             path, readonly=readonly
        )

    def __getitem__(self, item):
        if isinstance(item, (int, str)):
            return self._get_subcell(item)
        elif isinstance(item, slice):
            raise NotImplementedError  # TODO: x[min:max] outchannels
        else:
            raise TypeError(item)

    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if attr in type(self).__dict__ or attr in self.__dict__:
            return super().__getattribute__(attr)
        if attr == "schema":
            hcell = self._get_hcell()
            if hcell["celltype"] == "structured":
                cell = self._get_cell()
                ###schema = cell.get_schema() # wrong!
                struc_ctx = cell._data._context()
                schema = struc_ctx.example.handle.schema
                return SchemaWrapper(self, schema, "SCHEMA")
            else:
                raise AttributeError
        hcell = self._get_hcell()
        if not hcell["celltype"] == "structured":
            cell = self._get_cell()
            return getattr(cell, attr)
        return self._get_subcell(attr)

    def mount(self, path=None, mode="rw", authority="cell", persistent=True):
        """Mounts the cell to the file system.
        Mounting is only supported for non-structured cells.

        Arguments
        =========
        - path
          The file path on disk
        - mode
          "r" (read), "w" (write) or "rw".
          The mode can only contain "r" if the cell is authoritative.
          Default: "rw"
        - authority
          In case of conflict between cell and file, which takes precedence.
          Default: "cell".
        - persistent
          If False, the file is deleted from disk when the Cell is destroyed
        """
        assert self.celltype != "structured"
        hcell = self._get_hcell2()
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
        if self._parent() is not None:
            self._parent()._translate()
        return self

    def __setattr__(self, attr, value):
        if attr == "example":
            return getattr(self, "example").set(value)
        if attr.startswith("_") or hasattr(type(self), attr):
            return object.__setattr__(self, attr, value)
        return self._setattr(attr, value)

    def _setattr(self, attr, value):
        from .assign import assign_to_subcell
        parent = self._parent()

        if isinstance(value, Resource):
            value = value.data
        elif isinstance(value, Proxy):
            # TODO: implement for Transformer "code", "value", "schema", "example"
            raise NotImplementedError(value)

        hcell = self._get_hcell()
        if hcell.get("UNTRANSLATED"):
            raise Exception("Cell has not yet been translated")

        assign_to_subcell(self, (attr,), value)

    def connect_from(self, other):
        """Connect from another cell or transformer to this cell."""
        from .assign import assign
        parent = self._parent()
        return assign(parent, self._path, other)

    def __setitem__(self, item, value):
        if item in ("value", "schema"):
            raise NotImplementedError # TODO: might work on shadowed inchannels, but probably need to adapt assign_to_subcell
        if isinstance(item, str) and item.startswith("_"):
            raise NotImplementedError # TODO: might work on shadowed inchannels, but need to adapt __setattr__

        if isinstance(item, str):
            return setattr(self, item, value)
        elif isinstance(item, int):
            return self._setattr(item, value)
        else:
            raise TypeError(item)


    def traitlet(self):
        """Creates an traitlet object with its value linked to the cell.

        A traitlet is derived from ``traitlets.HasTraits``,
         and can be linked to other traitlet objects, such as ipywidgets.

        Examples
        ========
        - See basic-example.ipynb and datatables.ipynb
          in https://github.com/sjdv1982/seamless/tree/master/examples
        - See traitlets.ipynb, traitlet.py and traitlet2.py
          in https://github.com/sjdv1982/seamless/tree/master/tests/highlevel

        """
        hcell = self._get_hcell()
        trigger = not hcell.get("UNTRANSLATED")
        return self._parent()._add_traitlet(self._path, trigger)

    def output(self, layout=None):
        """Returns an output widget that tracks the cell value.

        The widget is a wrapper around an ``ipywidgets.Output``
        and is to be used in Jupyter.

        Examples
        ========
        - See basic-example.ipynb
          in https://github.com/sjdv1982/seamless/tree/master/examples
        - See traitlets.ipynb
          in https://github.com/sjdv1982/seamless/tree/master/tests/highlevel

        """
        from .OutputWidget import OutputWidget
        return OutputWidget(self, layout)

    @property
    def value(self):
        """Returns the value of the cell, if translated

        If the cell is not authoritative,
         the value is None if an upstream dependency
         is undefined or has an error.

        For structured cells, the value is also None if the
        schema is violated.
        """
        parent = self._parent()
        hcell = self._get_hcell()
        if hcell.get("UNTRANSLATED"):
            #return hcell["TEMP"]
            raise Exception("This cell is untranslated; run 'ctx.translate()' or 'await ctx.translation()'")
        try:
            cell = self._get_cell()
        except Exception:
            import traceback; traceback.print_exc()
            raise
        if cell is None:
            raise ValueError
        value = cell.value
        return value

    @property
    def buffered(self):
        """For a structured cell, return the buffered value.

        The buffered value is the value before schema validation"""
        parent = self._parent()
        hcell = self._get_hcell()
        if hcell.get("UNTRANSLATED") and "TEMP" in hcell:
            #return hcell["TEMP"]
            raise Exception # value untranslated; translation is async!
        assert hcell["celltype"] == "structured"
        try:
            cell = self._get_cell()
        except Exception:
            import traceback; traceback.print_exc()
            raise
        value = cell.buffer.value
        return value

    @property
    def example(self):
        """For a structured cell, return a dummy Silk handle.

        The handle does not store any values, but has type inference,
         i.e. schema properties are inferred from what is assigned to it.

        Examples
        ========
        - See basic-example.ipynb
          in https://github.com/sjdv1982/seamless/tree/master/examples
        """
        if self.celltype != "structured":
            raise AttributeError
        cell = self._get_cell()
        struc_ctx = cell._data._context()
        return struc_ctx.example.handle

    def add_validator(self, validator, name):
        """Adds a validator function (in Python) to the schema.

        The validator must take a single argument, the (buffered) value of the cell
        It is expected to raise an exception (e.g. an AssertionError)
        if the value is invalid.

        If a previous validator with the same name exists,
        that validator is overwritten.
        """
        return self.handle.add_validator(validator, name=name)

    @property
    def exception(self):
        """Returns the exception associated with the cell.

        For non-structured cells, this exception was raised during parsing.
        For structured cells, it may also have been raised during validation"""

        if self._get_hcell().get("UNTRANSLATED"):
            return None
        cell = self._get_cell()
        return cell.exception

    @property
    def checksum(self):
        """Contains the checksum of the cell, as SHA3-256 hash.

        The checksum defines the value of the cell.
        If the cell is defined, the checksum is available, even if
        the value may not be.
        """
        parent = self._parent()
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
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

    def observe(self, attr, callback, polling_interval, observe_none=False):
        """Adds an observer that monitors ``getattr(Cell, attr)``.

        This value is polled every `polling_interval` seconds,
        and if changed, ``callback(value)`` is invoked.

        If `observe_none`, None is considered as a separate value.
        (Default: False)

        This method is not recommended to observe cell values,
        this is better done with traitlets.

        Instead, it is recommended to use this to observe changes
        in status and exception.
        """

        if isinstance(attr, str):
            attr = (attr,)
        path = self._path + attr
        return self._get_top_parent().observe(
            path, callback, polling_interval,
            observe_none=observe_none
        )

    def unobserve(self, attr):
        """Stop observing ``getattr(Cell, attr)``"""
        if isinstance(attr, str):
            attr = (attr,)
        path = self._path + attr
        return self._get_top_parent().unobserve(path)

    async def fingertip(self):
        """Puts the buffer of this cell's checksum 'at your fingertips':

        - Verify that the buffer is locally or remotely available;
          if remotely, download it.
        - If not available, try to re-compute it using its provenance,
          i.e. re-evaluating any transformation or expression that produced it
        - Such recomputation is done in "fingertip" mode, i.e. disallowing
          use of expression-to-checksum or transformation-to-checksum caches
        """
        parent = self._parent()
        manager = parent._manager
        cachemanager = manager.cachemanager
        checksum = self.checksum
        await cachemanager.fingertip(checksum)

    @checksum.setter
    def checksum(self, checksum):
        """Sets the checksum of the cell, as SHA3-256 hash"""
        from ..silk import Silk
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            hcell["checksum"] = checksum
            return
        cell = self._get_cell()
        cell.set_checksum(checksum)

    @property
    def handle(self):
        assert self.celltype == "structured"
        cell = self._get_cell()
        if self.hash_pattern is not None:
            return cell.handle_hash
        else:
            return cell.handle_no_inference

    @property
    def data(self):
        """Returns the data of the cell

        This is normally the same as the value,
        but must not be modified"""
        cell = self._get_cell()
        return cell.data

    def _set(self, value):
        from ..core.structured_cell import StructuredCell
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            hcell["TEMP"] = value
            return
        cell = self._get_cell()
        if isinstance(cell, StructuredCell):
            cell.set_no_inference(value)
        else:
            cell.set(value)

    def set_checksum(self, checksum):
        from ..core.structured_cell import StructuredCell
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise NotImplementedError
        cell = self._get_cell()
        if isinstance(cell, StructuredCell):
            cell.set_auth_checksum(checksum)
        else:
            cell.set_checksum(checksum)

    @property
    def status(self):
        """Returns the status of the cell.

        The status may be undefined, error, upstream or OK
        If it is error, Cell.exception will be non-empty.
        """
        if self._get_hcell().get("UNTRANSLATED"):
            return None
        cell = self._get_cell()
        return cell.status

    def set(self, value):
        """Sets the value of the cell"""
        self._set(value)
        return self

    @property
    def celltype(self):
        """The type of the cell is by default "structured".

        Non-structured celltypes are:

        - "plain": contains any JSON-serializable data
        - "binary": contains binary data, wrapped in a Numpy object
        - "mixed": an arbitrary mixture of "plain" and "binary" data
        - "code": source code in any language
        - "text", "cson", "yaml"
        - "str", "bytes", "int", "float", "bool"
        """

        hcell = self._get_hcell2()
        return hcell["celltype"]

    @celltype.setter
    def celltype(self, value):
        assert value in celltypes, value
        hcell = self._get_hcell2()
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
        hcell["UNTRANSLATED"] = True
        if cellvalue is not None:
            hcell["TEMP"] = cellvalue
            hcell.pop("checksum", None)
        if self._parent() is not None:
            self._parent()._translate()

    @property
    def mimetype(self):
        """The mimetype of the cell.

        Can be set directly according to the MIME specification,
         or as a file extension.

        If not set, the default value depends on the celltype:

        - For structured cells, it is derived from the datatype attribute
        - For mixed cells, it is "seamless/mixed"
        - For code cells, it is derived from the language attribute
        - For plain cells and int/float/bool cells, it is "application/json"
        - For text cells and str cells, it is "text/plain"
        - For other cells, it is derived from their default file extension.
        """
        hcell = self._get_hcell2()
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
        hcell = self._get_hcell2()
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
        """ The datatype of a structured cell.
        As of Seamless 0.2, mostly an alternative for "mimetype"
        """
        hcell = self._get_hcell2()
        celltype = hcell["celltype"]
        assert celltype == "structured"
        return hcell["datatype"]

    @datatype.setter
    def datatype(self, value):
        hcell = self._get_hcell2()
        celltype = hcell["celltype"]
        assert celltype == "structured"
        hcell["datatype"] = value

    @property
    def scratch(self):
        """TODO: document"""
        hcell = self._get_hcell2()
        return ("scratch" in hcell)

    @scratch.setter
    def scratch(self, value):
        if value not in (True, False):
            raise TypeError(value)
        hcell = self._get_hcell2()
        if value == True:
            hcell["scratch"] = True
        else:
            hcell.pop("scratch", None)

    @property
    def fingertip_no_remote(self):
        """TODO: document"""
        hcell = self._get_hcell2()
        return hcell.get("fingertip_no_remote", False)

    @fingertip_no_remote.setter
    def fingertip_no_remote(self, value):
        if value not in (True, False):
            raise TypeError(value)
        hcell = self._get_hcell2()
        if value == True:
            hcell["fingertip_no_remote"] = True
        else:
            hcell.pop("fingertip_no_remote", None)

    @property
    def fingertip_no_recompute(self):
        """TODO: document"""
        hcell = self._get_hcell2()
        return hcell.get("fingertip_no_recompute", False)

    @fingertip_no_recompute.setter
    def fingertip_no_recompute(self, value):
        if value not in (True, False):
            raise TypeError(value)
        hcell = self._get_hcell2()
        if value == True:
            hcell["fingertip_no_recompute"] = True
        else:
            hcell.pop("fingertip_no_recompute", None)

    @property
    def hash_pattern(self):
        # TODO: document when released in 0.3
        hcell = self._get_hcell2()
        celltype = hcell["celltype"]
        assert celltype in ("structured", "mixed")
        return hcell["hash_pattern"]

    @hash_pattern.setter
    def hash_pattern(self, value):
        from ..core.protocol.deep_structure import validate_hash_pattern
        validate_hash_pattern(value)
        hcell = self._get_hcell2()
        celltype = hcell["celltype"]
        assert celltype in ("structured", "mixed")
        hcell["hash_pattern"] = value
        hcell.pop("checksum", None)
        if self._parent() is not None:
            self._parent()._translate()

    @property
    def language(self):
        """The programming language for code cells.

        Default: Python"""
        hcell = self._get_hcell2()
        celltype = hcell["celltype"]
        if celltype != "code":
            raise AttributeError
        return hcell.get("language", "python")

    @language.setter
    def language(self, value):
        from ..compiler import find_language
        hcell = self._get_hcell2()
        celltype = hcell["celltype"]
        if celltype != "code":
            return self._setattr("language", value)
        lang, language, extension = find_language(value)
        old_language = hcell.get("language")
        hcell["language"] = lang
        hcell["file_extension"] = extension
        if self._parent() is not None:
            self._parent()._translate()

    def __rshift__(self, other):
        assert isinstance(other, Proxy)
        assert "r" in other._mode
        assert other._pull_source is not None
        other._pull_source(self)

    def share(self, path=None, readonly=True):
        """Shares a cell over HTTP.

        Typically, the cell is available under
        http://localhost:5813/ctx/<path>.

        If path is None (default), Cell.path is used,
        with dots replaced by slashes.

        If readonly is True, only GET requests are supported.
        Else, the cell can also be modified using PUT requests
        using the Seamless JS client (js/seamless-client.js)

        Cells with mimetype 'application/json'
        (the default for plain cells)
        also support subcell GET requests,
        e.g. ``http://.../ctx/a/x/0`` for a cell ``ctx.a``
        with value ``{'x': [1,2,3] }``
        """
        assert readonly or self.authoritative
        assert readonly or self.celltype != "structured"
        hcell = self._get_hcell2()
        hcell["share"] = {
            "path": path,
            "readonly": readonly,
        }
        if self._parent() is not None:
            self._parent()._translate()
        return self

    def __dir__(self):
        result = [p for p in type(self).__dict__ if not p.startswith("_")]
        parent = self._parent()
        hcell = self._get_hcell()
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
        path = ".".join(self._path) if self._path is not None else None
        return "Seamless Cell: %s" % path

def cell_binary_method(self, other, name):
    h = self.handle
    method = getattr(h, name)
    if method is NotImplemented:
        return NotImplemented
    return method(other)


def Constant(*args, **kwargs):
    cell = Cell(*args, **kwargs)
    cell._get_hcell2()["constant"] = True

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
from .synth_context import SynthContext