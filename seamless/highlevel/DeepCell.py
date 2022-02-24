from copy import deepcopy

def get_new_deepcell(path):
    return {
        "path": path,
        "type": "deepcell",
        "UNTRANSLATED": True,
    }

from .Base import Base
from .HelpMixin import HelpMixin

class DeepCellBase(Base, HelpMixin):
    _node = None
    _virtual_path = None
    celltype = "structured"

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
            return hcell.get("checksum", {}).get("auth")
        else:
            cell = self._get_cell()
            return cell.checksum

    @checksum.setter
    def checksum(self, checksum):
        """Sets the checksum of the cell, as SHA3-256 hash"""
        self.set_checksum(checksum)
    
    def set_checksum(self, checksum):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            hcell.pop("TEMP", None)
            if hcell.get("checksum") is None:
                hcell["checksum"] = {}
            hcell["checksum"]["auth"] = checksum
            return
        cell = self._get_cell()
        cell.set_auth_checksum(checksum)

    @property
    def keyorder_checksum(self):
        """The checksum defining the key order of the deep cell"""
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            return hcell.get("checksum", {}).get("keyorder")
        else:
            cell = self._get_keyorder_cell()
            return cell.checksum

    @keyorder_checksum.setter
    def keyorder_checksum(self, checksum):
        """Sets the keyorder checksum, as SHA3-256 hash"""
        self.set_keyorder_checksum(checksum)

    def set_keyorder_checksum(self, checksum):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            if hcell.get("checksum") is None:
                hcell["checksum"] = {}
            hcell["checksum"]["keyorder"] = checksum
            return
        cell = self._get_keyorder_cell()
        cell.set_checksum(checksum)

    @property
    def handle(self):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        cell = self._get_cell()
        return cell.handle_hash

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

    @property
    def handle(self):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        cell = self._get_cell()
        return cell.handle_hash

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
            hcell.pop("TEMP", None)
            if hcell.get("checksum") is None:
                hcell["checksum"] = {}
            hcell["checksum"]["auth"] = checksum
            return
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

    @property
    def schema(self):
        raise AttributeError("DeepCell schemas are currently disabled.")

    def _get_cell_subpath(self, cell, subpath):
        p = cell
        for path in subpath:
            p2 = getattr(p, path)
            if isinstance(p2, SynthContext) and p2._context is not None:
                p2 = p2._context()
            p = p2
        return p

    def __setattr__(self, attr, value):
        if attr.startswith("_") or hasattr(type(self), attr):
            return object.__setattr__(self, attr, value)
        return self._setattr(attr, value)

    def _setattr(self, attr, value):
        from .assign import assign_to_deep_subcell
        assign_to_deep_subcell(self, attr, value)

    def _get_cell(self):
        parent = self._parent()
        p = parent._gen_context
        if p is None:
            raise ValueError
        pp = self._path[0]
        p2 = getattr(p, pp)
        if isinstance(p2, SynthContext) and p2._context is not None:
            p2 = p2._context()
        p = p2
        return self._get_cell_subpath(p, self._path[1:])

    def _get_keyorder_cell(self):
        parent = self._parent()
        p = parent._gen_context
        if p is None:
            raise ValueError
        path = self._path
        if len(self._path) > 1:
            pp = self._path[0]
            p2 = getattr(p, pp)
            if isinstance(p2, SynthContext) and p2._context is not None:
                p2 = p2._context()
            p = p2
            path = self._path[1:]
        path = path[:-1] + [path[-1] + "_KEYORDER"]
        return self._get_cell_subpath(p, path)

    def _get_hcell(self):
        parent = self._parent()
        return parent._get_node(self._path)

    def _get_hcell2(self):
        try:
            return self._get_hcell()
        except AttributeError:
            pass
        if self._node is None:
            self._node = self._new_func(None)
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
        if hcell.get("checksum") is None:
            hcell["checksum"] = {}
        hcell["checksum"].pop("buffer", None)
        if checksum is not None:
            hcell["checksum"]["buffer"] = checksum

    def _observe_keyorder(self, checksum):
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
        hcell["checksum"].pop("keyorder", None)
        if checksum is not None:
            hcell["checksum"]["keyorder"] = checksum

    def _set_observers(self):
        from ..core.structured_cell import StructuredCell
        cell = self._get_cell()
        if not isinstance(cell, StructuredCell):
            raise Exception(cell)
        if cell.auth is not None:
            cell.auth._set_observer(self._observe_auth)
        cell._data._set_observer(self._observe_cell)
        cell.buffer._set_observer(self._observe_buffer)
        keyorder_cell = self._get_keyorder_cell()
        keyorder_cell._set_observer(self._observe_keyorder)

    def _get_subcell(self, attr):
        hcell = self._get_hcell()
        parent = self._parent()
        readonly = False ### TODO
        return DeepSubCell(
            parent, self,
            attr, readonly=readonly
        )

    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if hasattr(type(self), attr) or attr in self.__dict__ or attr == "path":
            return super().__getattribute__(attr)
        hcell = self._get_hcell()
        return self._get_subcell(attr)

    def __dir__(self):
        result = [p for p in type(self).__dict__ if not p.startswith("_")]
        return result

    def __str__(self):
        return "Seamless DeepCell: " + self.path

    def __repr__(self):
        return str(self)

class DeepCell(DeepCellBase):
    _new_func = get_new_deepcell
    hash_pattern = {"*": "#"}

    def define(self, dataset:str, *, version:str=None, date:str=None, format:str=None, compression:str=None):
        import seamless
        from seamless.fair import get_distribution
        if version is None and date is None:
            version = "latest"
        if hasattr(seamless, "_defining_graph"):
            if version == "latest":
                print("""WARNING: defining a DeepCell from a FAIR data distribution 
with version "latest".
You should run this command in Jupyter/IPython and then use ctx.save().
Putting this code in define_graph is NOT REPRODUCIBLE.""")
        distribution = get_distribution(
            dataset, type="deepcell",
            version=version, date=date, format=format, compression=compression
        )
        
        self.set_checksum(distribution["checksum"])
        self.set_keyorder_checksum(distribution["keyorder"])
        hcell = self._get_hcell2()
        metadata = distribution.copy()
        metadata.pop("checksum")
        metadata.pop("keyorder")
        metadata.pop("latest", None)
        hcell["metadata"] = metadata
        
    @property
    def blacklist(self):
        # Similar to transformer.code
        raise NotImplementedError

    @property
    def whitelist(self):
        # Similar to transformer.code
        raise NotImplementedError

    def __getitem__(self, item):
        if isinstance(item, str):
            return self._get_subcell(item)
        else:
            raise TypeError(item)

"""
# YAGNI for now. 
# Unsupported by seamless.fair, and have to think of keyorder

def get_new_deeplistcell(path):
    return {
        "path": path,
        "type": "deeplistcell",
        "UNTRANSLATED": True,
    }


class DeepListCell(DeepCellBase):
    _new_func = get_new_deeplistcell

    def __getitem__(self, item):
        if isinstance(item, int):
            return self._get_subcell(item)
        elif isinstance(item, slice):
            raise NotImplementedError  # TODO: x[min:max] outchannels
        else:
            raise TypeError(item)
"""

from .synth_context import SynthContext
from .SubCell import DeepSubCell