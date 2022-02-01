from copy import deepcopy

def get_new_deepcell(path):
    return {
        "path": path,
        "type": "deepcell",
        "UNTRANSLATED": True,
    }

from .Base import Base
from .HelpMixin import HelpMixin

class DeepCell(Base, HelpMixin):
    _node = None

    def __init__(self, *, parent=None, path=None):
        assert (parent is None) == (path is None)
        if parent is not None:
            self._init(parent, path)

    def _init(self, parent, path):
        super().__init__(parent=parent, path=path)
        parent._children[path] = self

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
    def checksum(self):
        """Contains the checksum of the cell, as SHA3-256 hash.

        The checksum defines the value of the cell.
        If the cell is defined, the checksum is available, even if
        the value may not be.
        """
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            if "TEMP" in hcell:
                try:
                    cell = self._get_cell()
                    return cell.checksum
                except Exception:
                    raise AttributeError("TEMP value with unknown checksum")
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
        """Sets the checksum of the cell, as SHA3-256 hash"""
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            hcell.pop("TEMP", None)
            hcell["checksum"] = checksum
            return
        cell = self._get_cell()
        cell.set_checksum(checksum)

    @property
    def handle(self):
        assert self.celltype == "structured"
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        cell = self._get_cell()
        if self.hash_pattern is not None:
            return cell.handle_hash
        else:
            return cell.handle_no_inference

    @handle.setter
    def handle(self, value):
        self.handle.set(value)

    @property
    def data(self):
        """Returns the data of the cell

        The underlying checksums are NOT expanded to values
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

    def set_checksum(self, checksum):
        """Sets the cell's checksum from a SHA256 checksum"""
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
            return "Status: error (ctx needs translation)"
        cell = self._get_cell()
        return cell.status

    def set(self, value):
        """Sets the value of the cell"""
        self._set(value)
        return self

    @property
    def value(self):
        msg = """It is too costly to construct the full value of a DeepCell
Use DeepCell.data instead."""
        raise AttributeError(msg)

    def _get_cell_subpath(self, cell, subpath):
        p = cell
        for path in subpath:
            p2 = getattr(p, path)
            if isinstance(p2, SynthContext) and p2._context is not None:
                p2 = p2._context()
            p = p2
        return p

    def _get_cell(self):
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
            self._node = get_new_deepcell(None)
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

    def _set_observers(self):
        from ..core.structured_cell import StructuredCell
        cell = self._get_cell()
        if not isinstance(cell, StructuredCell):
            raise Exception(cell)
        if cell.auth is not None:
            cell.auth._set_observer(self._observe_auth)
        cell._data._set_observer(self._observe_cell)
        cell.buffer._set_observer(self._observe_buffer)
        if cell.schema is not None:
            cell.schema._set_observer(self._observe_schema)

    def __dir__(self):
        result = [p for p in type(self).__dict__ if not p.startswith("_")]
        return result

    def __str__(self):
        return "Seamless DeepCell: " + self.path

    def __repr__(self):
        return str(self)

from .synth_context import SynthContext