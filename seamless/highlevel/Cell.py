# Author: Sjoerd de Vries
# Copyright (c) 2016-2022 INSERM, 2022 CNRS

# The MIT License (MIT)

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Cell class for containing the checksum of a value,
and its helper functions."""

# pylint: disable=too-many-lines

from __future__ import annotations
from typing import *
from copy import deepcopy
from functools import partialmethod

from silk import Silk
from silk.mixed import MixedBase
from silk.SilkBase import binary_special_method_names
from .Base import Base
from .Resource import Resource
from .SelfWrapper import SelfWrapper
from ..mime import get_mime, language_to_mime, ext_to_mime
from .HelpMixin import HelpMixin

celltypes = (
    "structured",
    "text",
    "code",
    "plain",
    "mixed",
    "binary",
    "cson",
    "yaml",
    "str",
    "bytes",
    "int",
    "float",
    "bool",
    "checksum",
)


def get_new_cell(path: tuple(str, ...)) -> dict[str, Any]:
    """Return a workflow graph node for a new cell"""
    return {
        "path": path,
        "type": "cell",
        # "celltype": "structured",  # or "text" for help cells
        "datatype": "mixed",
        "hash_pattern": None,
        "UNTRANSLATED": True,
    }


class Cell(Base, HelpMixin):
    """Cell class. Contains the checksum of a value.

    See http://sjdv1982.github.io/seamless/sphinx/html/cell.html for documentation

    Typical usage:
    ```python
    # Explicit
    ctx.a = Cell("int").set(42)

    # Implicit
    ctx.a = 42
    ctx.a.celltype = "int"
    ```"""

    _virtual_path = None  # always None for cells
    _node: Optional[dict] = None  # temporary workflow graph node,
    #  while not yet part of a context
    _subpath: tuple[str, ...] = ()
    _fallback: Optional[Fallback] = None

    # pylint: disable=super-init-not-called
    def __init__(self, celltype: Optional[str] = None, *, parent=None, path=None):
        assert (parent is None) == (path is None)
        if parent is not None:
            self._init(parent, path)
        if celltype is not None:
            self.celltype = celltype

    def _init(self, parent, path):
        super().__init__(parent=parent, path=path)
        parent._set_child(path, self)
        self._node = None

    @property
    def independent(self) -> bool:
        """True if the cell has no dependencies"""
        parent = self._parent()
        if parent is None:
            return True
        connections = parent._graph.connections
        path = self._path
        lp = len(path)
        for con in connections:
            if con["type"] == "connection":
                if con["target"][:lp] == path:
                    return False
        return True

    def get_links(self) -> list:
        """Get all Link (bidirectional cell-cell) connections involving this cell."""
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
        """Version of _get_cell that creates a new node upon failure"""
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
            print(
                "WARNING: ignored value update for %s, because celltype changed" % self
            )
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
            print(
                "WARNING: ignored value update for %s, because celltype changed" % self
            )
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
            print(
                "WARNING: ignored value update for %s, because celltype changed" % self
            )
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

    @property
    def self(self):
        """Returns a wrapper where the subcells are not directly accessible.
        Only relevant for structured cells.

        By default, a structured cell with value {"status": 123} will cause
        "cell.status" to return "123", and not the actual cell status.

        To be sure to get the cell status, you can invoke cell.self.status.

        NOTE: experimental, requires more testing
        """
        attributelist = [k for k in type(self).__dict__ if not k.startswith("_")]
        return SelfWrapper(self, attributelist)

    def _get_subcell(self, attr):
        hcell = self._get_hcell()
        if hcell["type"] != "foldercell" and hcell["celltype"] != "structured":
            raise AttributeError(attr)
        parent = self._parent()
        readonly = False  # SubCell.__init__ may overrule this
        path = self._subpath + (attr,)
        return SubCell(parent, self._cell(), path, readonly=readonly)

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
        if hasattr(type(self), attr) or attr in self.__dict__ or attr == "path":
            return super().__getattribute__(attr)
        hcell = self._get_hcell()
        if attr == "schema":
            if hcell.get("UNTRANSLATED"):
                raise AttributeError(
                    "Cannot access Cell.schema: cell must be translated first"
                )
            if hcell["celltype"] == "structured":
                cell = self._get_cell()
                schema = self.example.schema
                return SchemaWrapper(self, schema, "SCHEMA")
            raise AttributeError
        if not hcell["celltype"] == "structured":
            cell = self._get_cell()
            return getattr(cell, attr)
        return self._get_subcell(attr)

    @property
    def fallback(self) -> Fallback:
        """Get a Fallback object
        With this, you can set and activate a fallback Cell, which will
        provide an alternative value once the fallback is activated."""
        return Fallback(self)

    def mount(
        self,
        path: str,
        mode: str = "rw",
        authority: str = "file",
        *,
        persistent: bool = True
    ):
        """Mounts the cell to the file system.
        Mounting is only supported for non-structured cells.

        To delete an existing mount, do `del cell.mount`

        Arguments
        =========
        - path
            The file path on disk
        - mode
            "r" (read), "w" (write) or "rw".
            If the mode contains "r", the cell is updated when the file changes on disk.
            If the mode contains "w", the file is updated when the cell value changes.
            The mode can only contain "r" if the cell is independent.
            Default: "rw"
        - authority
            In case of conflict between cell and file, which takes precedence.
            Default: "file".
        - persistent
            If False, the file is deleted from disk when the Cell is destroyed
            Default: True."""
        if self.celltype == "structured" and not isinstance(self, FolderCell):
            raise Exception("Mounting is only supported for non-structured cells")

        if "r" in mode and not self.independent:
            msg = """Cannot mount {} in read mode.
This cell is not fully independent, i.e. it has incoming connections"""
            raise Exception(msg.format(self))

        # TODO, upon translation: check that there are no duplicate paths.
        hcell = self._get_hcell2()
        mount = {
            "path": path,
            "mode": mode,
            "authority": authority,
            "persistent": persistent,
        }
        hcell["mount"] = mount
        hcell["UNTRANSLATED"] = True
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

        self._parent()

        if isinstance(value, Resource):
            value = value.data
        elif isinstance(value, Proxy):
            # TODO: implement for Transformer "code", "value", "schema", "example"
            raise NotImplementedError(value)

        assign_to_subcell(self, (attr,), value)

    def connect_from(self, other: Cell | Transformer) -> None:
        """Connect from another cell or transformer to this cell."""
        from .assign import assign

        parent = self._parent()
        assign(parent, self._path, other)

    def __setitem__(self, item, value):
        if item in ("value", "schema"):
            raise NotImplementedError  # TODO: might work on shadowed inchannels,
            # but probably need to adapt assign_to_subcell
        if isinstance(item, str) and item.startswith("_"):
            raise NotImplementedError  # TODO: might work on shadowed inchannels,
            #  but need to adapt __setattr__
        if isinstance(item, str):
            return setattr(self, item, value)
        elif isinstance(item, int):
            return self._setattr(item, value)
        else:
            raise TypeError(item)

    def traitlet(self) -> SeamlessTraitlet:
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

    def output(self, layout: Optional[dict] = None) -> OutputWidget:
        """Returns an output widget that tracks the cell value.

        The widget is a wrapper around an ``ipywidgets.Output``
        and is to be used in Jupyter.

        "layout" is a dict that is passed on directly to ``ipywidgets.Output``

        Examples
        ========
        - See basic-example.ipynb
            in https://github.com/sjdv1982/seamless/tree/master/examples
        - See traitlets.ipynb
            in https://github.com/sjdv1982/seamless/tree/master/tests/highlevel
        """
        return OutputWidget(self, layout)

    @property
    def value(self):
        """Returns the value of the cell, if translated

        If the cell is not independent,
            the value is None if an upstream dependency
            is undefined or has an error.

        For structured cells, the value is also None if the
        schema is violated."""
        '''
        if self.hash_pattern:
            msg = """It is too costly to construct the full value of a deep cell
    Use cell.data instead.
    
    If you are really sure that the value of the deep cell fits in memory,
    you can assign this cell to a normal cell, e.g:
    
    ctx.othercell = Cell()
    ctx.othercell = ctx.thiscell
    """
            raise AttributeError(msg)
        '''
        self._parent()
        hcell = self._get_hcell()
        if hcell.get("UNTRANSLATED"):
            if self._path[0] == "HELP":
                return hcell.get("TEMP")
            return None
        try:
            cell = self._get_cell()
        except Exception:
            import traceback

            traceback.print_exc()
            raise
        if cell is None:
            raise ValueError
        value = cell.value
        return value

    @property
    def buffered(self):
        """For a structured cell, return the buffered value.

        The buffered value is the value before schema validation"""
        self._parent()
        hcell = self._get_hcell()
        if hcell.get("UNTRANSLATED") and "TEMP" in hcell:
            # return hcell["TEMP"]
            raise Exception  # value untranslated; translation is async!
        assert hcell["celltype"] == "structured"
        try:
            cell = self._get_cell()
        except Exception:
            import traceback

            traceback.print_exc()
            raise
        value = cell.buffer.value
        return value

    @property
    def example(self) -> Silk:
        """For a structured cell, return a dummy Silk handle.

        The handle does not store any values, but has type inference,
            i.e. schema properties are inferred from what is assigned to it.

        Examples
        ========
        - See basic-example.ipynb
            in https://github.com/sjdv1982/seamless/tree/master/examples"""
        if self.celltype != "structured":
            raise AttributeError
        cell = self._get_cell()
        struc_ctx = cell._data._context()
        return struc_ctx.example.handle

    def add_validator(self, validator: Callable, name: str) -> None:
        """Adds a validator function (in Python)def add to the schema.

        The validator must take a single argument, the (buffered) value of the cell
        It is expected to raise an exception (e.g. an AssertionError)
        if the value is invalid.

        If a previous validator with the same name exists,
        that validator is overwritten."""
        if self._get_hcell().get("UNTRANSLATED"):
            raise AttributeError(
                "Cannot invoke Cell.add_validator: cell must be translated first"
            )
        return self.handle.add_validator(validator, name=name)

    @property
    def exception(self):
        """Returns the exception associated with the cell.

        For non-structured cells, this exception was raised during parsing.
        For structured cells, it may also have been raised during validation"""

        if self._get_hcell().get("UNTRANSLATED"):
            return "This cell is untranslated; run 'ctx.translate()' or 'await ctx.translation()'"
        cell = self._get_cell()
        return cell.exception

    @property
    def checksum(self) -> Optional[str]:
        """Contains the checksum of the cell, as SHA3-256 hash.

        The checksum defines the value of the cell.
        If the cell is defined, the checksum is available, even if
        the value may not be."""
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            if "TEMP" in hcell:
                try:
                    cell = self._get_cell()
                    return cell.checksum
                except Exception:
                    raise AttributeError("TEMP value with unknown checksum") from None
            return hcell.get("checksum")
        else:
            cell = self._get_cell()
            return cell.checksum

    def observe(
        self,
        attr: str | tuple[str, ...],
        callback: Callable,
        polling_interval: float,
        observe_none: bool = False,
    ):
        """Adds an observer that monitors ``getattr(Cell, attr)``.

        This value is polled every `polling_interval` seconds,
        and if changed, ``callback(value)`` is invoked.

        If `observe_none`, None is considered as a separate value.
        (Default: False)

        This method is not recommended to observe cell values,
        this is better done with traitlets.

        Instead, it is recommended to use this to observe changes
        in status and exception."""

        if isinstance(attr, str):
            attr = (attr,)
        path = self._path + attr
        return self._get_top_parent().observe(
            path, callback, polling_interval, observe_none=observe_none
        )

    def unobserve(self, attr: str | tuple[str, ...]):
        """Stop observing ``getattr(Cell, attr)``"""
        if isinstance(attr, str):
            attr = (attr,)
        path = self._path + attr
        return self._get_top_parent().unobserve(path)

    async def fingertip(self) -> None:
        """Puts the buffer of this cell's checksum 'at your fingertips':

        - Verify that the buffer is locally or remotely available;
            if remotely, download it.
        - If not available, try to re-compute it using its provenance,
            i.e. re-evaluating any transformation or expression that produced it
        - Such recomputation is done in "fingertip" mode, i.e. disallowing
            use of expression-to-checksum or transformation-to-checksum caches"""
        parent = self._parent()
        manager = parent._manager
        cachemanager = manager.cachemanager
        checksum = self.checksum
        await cachemanager.fingertip(checksum)

    @checksum.setter
    def checksum(self, checksum:Optional[str]):
        """Set the checksum of the cell, as SHA3-256 hash"""
        self.set_checksum(checksum)

    @property
    def handle(self):
        """Return a Silk handle to a structured cell.

        This is a Silk wrapper around the authoritative
        (independent) part of a structured cell.
        """
        assert self.celltype == "structured"
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        cell = self._get_cell()
        if self.hash_pattern is not None:
            return cell.handle_hash
        else:
            return cell.handle_no_inference

    @property
    def _data(self):
        """Return the data of the cell

        This is normally the same as the value.def _set(
        """
        cell = self._get_cell()
        return deepcopy(cell.data)

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

    def set_buffer(self, value):
        from ..core.structured_cell import StructuredCell

        if not self.independent:
            raise TypeError("Cannot set the buffer of a cell that is not independent")

        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            hcell["TEMP"] = value
            return
        cell = self._get_cell()
        cell.set_buffer(value)
        return self

    def set_checksum(self, checksum:str):
        """Set the cell's checksum from a SHA256 checksum"""
        from ..core.structured_cell import StructuredCell

        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise NotImplementedError
        cell = self._get_cell()
        if isinstance(cell, StructuredCell):
            cell.set_auth_checksum(checksum)
        else:
            if not self.independent:
                raise TypeError("Cannot set the checksum of a cell that is not independent")
            cell.set_checksum(checksum)

    @property
    def status(self):
        """Return the status of the cell.

        The status may be undefined, error, upstream or OK
        If it is error, Cell.exception will be non-empty."""
        if self._get_hcell().get("UNTRANSLATED"):
            return "Status: error (ctx needs translation)"
        cell = self._get_cell()
        return cell.status

    def set(self, value):
        """Set the value of the cell"""
        if not self.independent:
            raise TypeError("Cannot set the value of a cell that is not independent")
        self._set(value)
        return self

    @property
    def celltype(self) -> str:
        """The type of the cell.

        The type of the cell is by default "structured",
        unless it is a help cell, which are "text" by default.

        Non-structured celltypes are:

        - "plain": contains any JSON-serializable data
        - "binary": contains binary data, wrapped in a Numpy object
        - "mixed": an arbitrary mixture of "plain" and "binary" data
        - "code": source code in any language
        - "text", "cson", "yaml"
        - "str", "bytes", "int", "float", "bool" """

        hcell = self._get_hcell2()
        return hcell["celltype"]

    @celltype.setter
    def celltype(self, value:str):
        if not isinstance(value, str):
            raise TypeError(type(value))
        assert value in celltypes, value
        hcell = self._get_hcell2()
        if hcell.get("celltype", "structured") == value:
            return
        if hcell.get("UNTRANSLATED"):
            cellvalue = hcell.get("TEMP")
        else:
            if value == "structured":
                if "mount" in hcell:
                    raise ValueError(
                        "Mounting is only supported for non-structured cells"
                    )
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
            if self.independent:
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
        - For other cells, it is derived from their default file extension."""
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
            if datatype in ("mixed", "binary", "plain"):
                mimetype = get_mime(datatype)
            elif datatype in ("float", "int", "str", "bool"):
                mimetype = get_mime("plain")
            else:
                mimetype = ext_to_mime(datatype)
        else:
            mimetype = get_mime(celltype)
        return mimetype

    @mimetype.setter
    def mimetype(self, value):
        hcell = self._get_hcell2()
        if value is None:
            hcell.pop("mimetype", None)
            hcell.pop("file_extension", None)
        else:
            if value.find("/") == -1:
                try:
                    ext = value
                    value = ext_to_mime(ext)
                except KeyError:
                    raise ValueError("Unknown extension %s" % ext) from None
                hcell["file_extension"] = ext
            hcell["mimetype"] = value
        hcell["UNSHARE"] = True
        if self._parent() is not None:
            self._parent()._translate()

    @property
    def datatype(self):
        """The datatype of a structured cell.
        This makes it possible to indicate that a structural cell conforms
        to another Seamless celltype and can be trivially converted to it.
        Use cases:
        - "plain" or "binary" cells with subcell access and a schema
        - "str" or "bytes" cell with a validator schema that parses the content
        - sharing a structured cell over HTTP using the Seamless web interface generator
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
        if value is None:
            hcell.pop("datatype", None)
        else:
            if value == "bytes":
                raise TypeError("Byte cells and structured cells are stored differently.")
            elif value == "text":
                raise TypeError("""
Text cells and structured cells are stored differently.

For use in web forms, instead use "str".
For other use in HTTP requests, instead set mimetype to "text/plain".
""")
        hcell["datatype"] = value

    @property
    def scratch(self) -> bool:
        """Is the cell a scratch cell.

        Scratch cells are fully dependent cells that are big and/or easy to
        recompute.
        TODO: enforce that scratch cells must be fully dependent.

        Scratch cell buffers are:
        - Not added to saved zip archives and vaults.
        - TODO: Annotated as "scratch" in databases
        - TODO: cleared automatically from databases a short while after computation
        """
        hcell = self._get_hcell2()
        return "scratch" in hcell

    @scratch.setter
    def scratch(self, value:bool):
        if value not in (True, False):
            raise TypeError(value)
        hcell = self._get_hcell2()
        if value:
            hcell["scratch"] = True
        else:
            hcell.pop("scratch", None)

    @property
    def fingertip_no_remote(self) -> bool:
        """If True, remote calls are disabled for fingertipping.

        Remote calls can be for a database or a buffer server.
        """
        hcell = self._get_hcell2()
        return hcell.get("fingertip_no_remote", False)

    @fingertip_no_remote.setter
    def fingertip_no_remote(self, value:bool):
        if value not in (True, False):
            raise TypeError(value)
        hcell = self._get_hcell2()
        if value:
            hcell["fingertip_no_remote"] = True
        else:
            hcell.pop("fingertip_no_remote", None)

    @property
    def fingertip_no_recompute(self) -> bool:
        """If True, recomputation is disabled for fingertipping.

        This means recomputation via a transformer, which can be intensive.
        Recomputation via conversion or subcell expression (which are quick)
        is always enabled.
        """
        hcell = self._get_hcell2()
        return hcell.get("fingertip_no_recompute", False)

    @fingertip_no_recompute.setter
    def fingertip_no_recompute(self, value:bool):
        if value not in (True, False):
            raise TypeError(value)
        hcell = self._get_hcell2()
        if value:
            hcell["fingertip_no_recompute"] = True
        else:
            hcell.pop("fingertip_no_recompute", None)

    @property
    def hash_pattern(self):
        """The hash pattern of the cell.

        This is an advanced feature, not used in day-to-day programming.
        Possible values:
        - {"*": "#"} . The cell will behave as a deep cell.
        - {"*": "##"} . The cell will behave as a deep folder.
        - {"!": "#"} . The cell will behave as a deep list
         (a list of mixed checksums).

        Note that all usual safety guards provided by DeepCell and
        DeepFolder are absent. You can invoke Cell.value,
        or do similar things that may consume all of your memory.
        """
        hcell = self._get_hcell2()
        celltype = hcell["celltype"]
        if celltype not in ("structured", "mixed"):
            return None
        return hcell["hash_pattern"]

    @hash_pattern.setter
    def hash_pattern(self, value):
        from ..core.protocol.deep_structure import validate_hash_pattern

        hcell = self._get_hcell2()
        if value is None:
            hcell.pop("hash_pattern", None)
        else:
            validate_hash_pattern(value)
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
        hcell = self._get_hcell2()
        celltype = hcell["celltype"]
        if celltype != "code":
            return self._setattr("language", value)
        parent = self._parent()
        old_language = hcell.get("language")
        if value is None:
            hcell.pop("language", None)
            hcell.pop("file_extension", None)
        else:
            lang, _, extension = parent.environment.find_language(value)
            hcell["language"] = lang
            hcell["file_extension"] = extension
        if lang != old_language:
            if self._parent() is not None:
                self._parent()._translate()

    def share(self, path=None, readonly=True, *, toplevel=False):
        """Share a cell over HTTP.

        Typically, the cell is available under
        http://localhost:5813/ctx/<path>.

        If path is None (default), Cell.path is used,
        with dots replaced by slashes.

        If toplevel is True, the cell is instead available under
        http://localhost:5813/<path>.

        If readonly is True, only GET requests are supported.
        Else, the cell can also be modified using PUT requests
        using the Seamless JS client (js/seamless-client.js)

        Cells with mimetype 'application/json'
        (the default for plain cells)
        also support subcell GET requests,
        e.g. ``http://.../ctx/a/x/0`` for a cell ``ctx.a``
        with value ``{'x': [1,2,3] }``

        To remove a share, do `del cell.share`"""
        if not readonly:
            if not self.independent:
                msg = """{}: Non-readonly HTTP share is not possible.
This cell is not fully independent, i.e. it has incoming connections"""
                raise Exception(msg.format(self))

        assert readonly or self.independent
        hcell = self._get_hcell2()
        hcell["share"] = {
            "path": path,
            "readonly": readonly,
        }
        if toplevel:
            hcell["share"]["toplevel"] = True
        hcell["UNSHARE"] = True
        if self._parent() is not None:
            self._parent()._translate()
        return self

    def __dir__(self):
        result = [p for p in type(self).__dict__ if not p.startswith("_")]
        self._parent()
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
            if not isinstance(self, FolderCell):
                cell.buffer._set_observer(self._observe_buffer)
            if cell.schema is not None:
                cell.schema._set_observer(self._observe_schema)
        else:
            cell._set_observer(self._observe_cell)

    def __delattr__(self, attr):
        if attr.startswith("_"):
            return super().__delattr__(attr)
        if attr in ("share", "mount"):
            hcell = self._get_hcell2()
            if attr in hcell:
                hcell.pop(attr)
                if self._parent() is not None:
                    self._parent()._translate()
        elif attr in ("scratch", "fingertip_no_remote", "fingertip_no_recompute"):
            setattr(self, attr, False)
        elif attr in ("hash_pattern", "mimetype", "language", "checksum", "datatype"):
            setattr(self, attr, None)
        else:
            raise AttributeError(attr)

    def __str__(self):
        return "Seamless Cell: " + self.path

    def __repr__(self):
        return str(self)


def _cell_binary_method(self, other, name):
    hcell = self._get_hcell()
    is_simple = False
    if hcell.get("UNTRANSLATED") and "TEMP" in hcell:
        obj = hcell["TEMP"]    
    elif self.celltype == "structured":
        obj = self.handle
    else:
        is_simple = True
        obj = self.value

    try:
        method = getattr(obj, name)
    except AttributeError:
        return NotImplemented
    if method is NotImplemented:
        return NotImplemented
    result = method(other)
    if is_simple:
        self.set(result)
    return result


def get_new_foldercell(path):
    """Return a workflow graph node for a new folder cell"""
    return {
        "path": path,
        "type": "foldercell",
        "UNTRANSLATED": True,
    }


class FolderCell(Cell):
    """Cell that contains the content of a file system directory

    The content is a dictionary where the file names are strings.
    The dictionary is flat: subdirectories are stored as file names with slashes.

    Internally, the dictionary is stored as a deep cell to save memory.
    However, it is assumed that the content does fit in memory,
    since FolderCell.value is allowed and returns the full directory content.

    For datasets that do not fit in memory, use DeepFolderCell instead.
    """
    def _get_hcell2(self):
        try:
            return self._get_hcell()
        except AttributeError:
            pass
        if self._node is None:
            self._node = get_new_foldercell(None)
        return self._node

    @property
    def celltype(self):
        return "structured"

    @celltype.setter
    def celltype(self, value):
        raise AttributeError("celltype")

    @property
    def hash_pattern(self):
        return {"*": "##"}

    @property
    def data(self):
        """Returns the data (deep checksum dict) of the folder"""
        cell = self._get_cell()
        return deepcopy(cell.data)

    def _setattr(self, attr, value):
        hcell = self._get_hcell()
        if "mount" in hcell:
            if "r" in hcell["mount"]["mode"]:
                msg = "Cannot assign to '{}': Folder is mounted to the file system in read mode"
                raise AttributeError(msg.format(attr))
        return super()._setattr(attr, value)

    def mount(
        self, path, mode, *, persistent=True, text_only=False
    ):  # pylint: disable=arguments-differ
        """Mounts the FolderCell to the file system.
        "path" is the path to the file system directory.

        "mode" must be specified and must be "r" or "w".

        - persistent
            If False, the directory is deleted from disk when the FolderCell is destroyed
            Default: True.

        - text_only
            If True, only text buffers are read from disk or written to disk.
            Non-text buffers (i.e. file content or buffers that cannot be encoded to UTF-8)
            are skipped.
            Default: False.


        To delete an existing mount, do `del foldercell.mount`"""
        if mode not in ("r", "w"):
            raise ValueError('Mode must be "r" or "w"')
        if mode == "r":
            hcell = self._get_hcell2()
            hcell.pop("checksum", None)
        super().mount(path, mode, "cell", persistent=persistent)
        if text_only:
            hcell = self._get_hcell2()
            hcell["mount"]["text_only"] = True
        return self

    def __str__(self):
        return "Seamless FolderCell: " + self.path


def Constant(*args, **kwargs):
    """Construct a cell marked as "constant"."""
    cell = Cell(*args, **kwargs)
    cell._get_hcell2()["constant"] = True
    return cell

def SimpleDeepCell():
    """Construct a mixed cell with a deep hash pattern."""
    cell = Cell()
    node = cell._get_hcell2()
    node["celltype"] = "mixed"
    node["hash_pattern"] = {"*": "#"}
    return cell

for _ in binary_special_method_names:
    if _ in Cell.__dict__:
        continue
    m = partialmethod(_cell_binary_method, name=_)
    setattr(Cell, _, m)

from .SubCell import SubCell
from .SchemaWrapper import SchemaWrapper
from .proxy import Proxy
from .synth_context import SynthContext
from .Fallback import Fallback
from .OutputWidget import OutputWidget
from .SeamlessTraitlet import SeamlessTraitlet
from .Transformer import Transformer
