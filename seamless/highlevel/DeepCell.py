from copy import deepcopy
from functools import partial

def get_new_deepcell(path):
    from ..core.cache.buffer_cache import empty_list_checksum, empty_dict_checksum
    return {
        "path": path,
        "type": "deepcell",
        "UNTRANSLATED": True,
        "checksum": {
            "origin": empty_dict_checksum,
            "keyorder": empty_list_checksum,
        }
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
        """Returns the exception associated with the deep cell."""

        if self._get_hcell().get("UNTRANSLATED"):
            return "This cell is untranslated; run 'ctx.translate()' or 'await ctx.translation()'"
        ctx = self._get_context()
        attrs = ("origin", "keyorder", "blacklist", "whitelist", "apply_blackwhite", "filtered", "filtered_keyorder")
        for k in attrs:
            exception = getattr(ctx, k).exception
            if exception is not None:
                    if k == "origin":
                        return exception
                    else:
                        return "*" + k + "*: " + exception
    
    @property
    def checksum(self):
        """Contains the checksum of the cell, as SHA3-256 hash.

The checksum defines the value of the cell.
If the cell is defined, the checksum is available, even if
the value may not be.
"""
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            return hcell.get("checksum", {}).get("origin")
        else:
            ctx = self._get_context()
            return ctx.origin.checksum

    @checksum.setter
    def checksum(self, checksum):
        """Sets the checksum of the cell, as SHA3-256 hash"""
        self.set_checksum(checksum)
    
    def set_checksum(self, checksum):
        from ..core.cache.buffer_cache import empty_dict_checksum
        hcell = self._get_hcell2()
        hcell.pop("metadata", None)
        if hcell.get("UNTRANSLATED"):
            hcell.pop("TEMP", None)
            if hcell.get("checksum") is None:
                hcell["checksum"] = {}
            hcell["checksum"]["origin"] = checksum
            return
        ctx = self._get_context()
        origin_cell = ctx.origin
        if checksum is None:
            checksum = empty_dict_checksum
        origin_cell.set_auth_checksum(checksum)

    @property
    def keyorder(self):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        else:
            ctx = self._get_context()
            cell = ctx.keyorder
            return cell.value

    @keyorder.setter
    def keyorder(self, keyorder):
        if keyorder is None:
            return self.set_keyorder_checksum(None)
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        ctx = self._get_context()
        cell = ctx.keyorder
        cell.set(keyorder)
        
    @property
    def keyorder_checksum(self):
        """The checksum defining the key order of the deep cell"""
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            return hcell.get("checksum", {}).get("keyorder")
        else:
            ctx = self._get_context()
            cell = ctx.keyorder
            return cell.checksum

    @keyorder_checksum.setter
    def keyorder_checksum(self, checksum):
        """Sets the keyorder checksum, as SHA3-256 hash"""
        self.set_keyorder_checksum(checksum)

    def set_keyorder_checksum(self, checksum):
        from ..core.cache.buffer_cache import empty_list_checksum
        hcell = self._get_hcell2()
        hcell.pop("metadata", None)
        if hcell.get("UNTRANSLATED"):
            if hcell.get("checksum") is None:
                hcell["checksum"] = {}
            hcell["checksum"]["keyorder"] = checksum
            return
        ctx = self._get_context()
        cell = ctx.keyorder
        if checksum is None:
            checksum = empty_list_checksum
        cell.set_checksum(checksum)

    @property
    def data(self):
        """Returns the data of the cell

        The underlying checksums are NOT expanded to values
        """
        ctx = self._get_context()
        cell = ctx.origin
        return deepcopy(cell.data)

    @property
    def handle(self):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        ctx = self._get_context()
        cell = ctx.origin
        return cell.handle_hash

    def set(self, value):
        self.handle.set(value)

    @property
    def status(self):
        """Returns the status of the DeepCell.

        The status may be undefined, pending, error or OK
        If it is error, DeepCell.exception will be non-empty.
        """
        if self._get_hcell().get("UNTRANSLATED"):
            return "Status: error (ctx needs translation)"
        ctx = self._get_context()
        attrs = ("origin", "keyorder", "blacklist", "whitelist", "apply_blackwhite", "filtered", "filtered_keyorder")
        for k in attrs:
            pending = False
            upstream = False
            status = getattr(ctx, k).status
            if k != "origin" and status.endswith("undefined"):
                continue
            if not status.endswith("OK"):
                if status.endswith(" pending"):
                    pending = True
                elif status.endswith(" upstream"):
                    upstream = True
                else:
                    if k == "origin":
                        return status
                    else:
                        return "*" + k + "*: " + status
        if upstream:
            return "Status: upstream"
        elif pending:
            return "Status: pending"
        return "Status: OK"

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

    def _get_context(self):
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

    def _observe(self, key, checksum):
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
        hcell["checksum"].pop(key, None)
        if checksum is not None:
            hcell["checksum"][key] = checksum


    def _set_observers(self):
        from ..core.structured_cell import StructuredCell
        ctx = self._get_context()
        ctx.origin.auth._set_observer(partial(self._observe, "origin"))
        ctx.keyorder._set_observer(partial(self._observe, "keyorder"))
        ctx.filtered0._set_observer(partial(self._observe, "filtered"))
        ctx.blacklist._set_observer(partial(self._observe, "blacklist"))
        ctx.whitelist._set_observer(partial(self._observe, "whitelist"))

    def _get_subcell(self, attr):
        self._get_hcell()
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

    @staticmethod
    def find_distribution(dataset:str, *, version:str=None, date:str=None, format:str=None, compression:str=None):
        from seamless.fair import find_distribution
        distribution = find_distribution(
            dataset, type="deepcell",
            version=version, date=date, format=format, compression=compression
        )
        print("""WARNING: finding a FAIR data distribution for a DeepCell
is only weakly reproducible.
To guarantee strong reproducibility:
- Use "DeepCell().define(DeepCell.find_distribution(...))" only in IPython 
  and then use ctx.save().
OR: 
- If you prefer to use load_project.py:define_graph, enter the following code:

    distribution = {{
        "checksum": "{}",
        "keyorder": "{}",
    }}
    DeepCell().define(distribution)
    
""".format(distribution["checksum"], distribution["keyorder"]))

        return distribution

    def define(self, distribution):
        from seamless.fair import find
        self.set_checksum(distribution["checksum"])
        self.set_keyorder_checksum(distribution["keyorder"])
        meta_keys = ["content_size", "index_size", "nkeys", "access_index"]
        if not all([key in distribution for key in meta_keys]):
            try:
                distribution2 = None
                result = find(distribution["checksum"])
                if result is not None:
                    dataset, distribution2 = result["dataset"], result["distribution"]
                if distribution2 is not None:
                    metadata = {"dataset": dataset}
                    for key in meta_keys:
                        if key in distribution2:
                            metadata[key] = distribution2[key]
                    self._get_hcell()["metadata"] = metadata
            except Exception:
                pass
        

    def _get_bwlist(self, bw):
        ctx = self._get_context()
        cell = getattr(ctx, bw)
        return cell.value

    def _set_bwlist(self, bw, value):
        from .assign import assign_connection
        from .Cell import Cell
        if value is None or isinstance(value, (list, tuple)):
            ctx = self._get_context()
            cell = getattr(ctx, bw)
            cell.set(value)
        elif isinstance(value, Cell):
            ctx = self._parent()
            assert value._parent() is ctx #no connections between different (toplevel) contexts
            assign_connection(ctx, value._path, self._path + (bw,), False)
            hcell = self._get_hcell2()
            hcell.pop("TEMP", None)
            if hcell.get("checksum") is not None:
                hcell["checksum"].pop(bw, None)
            self._parent()._translate()
        else:
            raise TypeError(type(value))

    @property
    def blacklist(self):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        return self._get_bwlist("blacklist")

    @blacklist.setter
    def blacklist(self, value):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        return self._set_bwlist("blacklist", value)

    @property
    def whitelist(self):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        return self._get_bwlist("whitelist")

    @whitelist.setter
    def whitelist(self, value):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        return self._set_bwlist("whitelist", value)

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