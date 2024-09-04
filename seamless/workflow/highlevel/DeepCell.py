"""DeepCell class and support functions"""

from copy import deepcopy
from functools import partial

from seamless import Checksum
from seamless.util import fair
from seamless.checksum import empty_list_checksum, empty_dict_checksum
from seamless.checksum.deserialize import deserialize_sync as deserialize


def get_new_deepcell(path):
    """Create a new DeepCell node for the nodegraph"""
    return {
        "path": path,
        "type": "deepcell",
        "UNTRANSLATED": True,
        "checksum": {
            "origin": empty_dict_checksum,
            "keyorder": empty_list_checksum,
        },
    }


def get_new_deepfoldercell(path):
    """Create a new DeepFolderCell node for the nodegraph"""
    return {
        "path": path,
        "type": "deepfoldercell",
        "UNTRANSLATED": True,
        "checksum": {
            "origin": empty_dict_checksum,
            "keyorder": empty_list_checksum,
        },
    }


from .Base import Base
from .HelpMixin import HelpMixin


class DeepCellBase(Base, HelpMixin):
    """Base class for deep cells.
    Deep cells are cells whose value is a dict of checksums"""

    _node = None
    _virtual_path = None  # always None for deep cells
    celltype = "structured"
    _components = (
        "origin",
        "keyorder",
        "blacklist",
        "whitelist",
        "apply_blackwhite",
        "integrate_options",
        "filtered",
        "filtered_keyorder",
    )

    def __init__(
        self, *, parent=None, path=None
    ):  # pylint: disable=super-init-not-called
        assert (parent is None) == (path is None)
        if parent is not None:
            self._init(parent, path)

    def _init(self, parent, path):
        super().__init__(parent=parent, path=path)
        parent._set_child(path, self)

    @property
    def exception(self):
        """Returns the exception associated with the deep cell."""

        if self._get_hcell().get("UNTRANSLATED"):
            return "This cell is untranslated; run 'ctx.translate()' or 'await ctx.translation()'"
        ctx = self._get_context()
        for k in self._components:
            if k == "integrate_options" and not hasattr(ctx, k):
                continue
            exception = getattr(ctx, k).exception
            if exception is not None:
                if k == "origin":
                    return exception
                else:
                    return "*" + k + "*: " + exception

    @property
    def checksum(self) -> Checksum:
        """Contains the checksum of the cell, as SHA3-256 hash.

        The checksum defines the value of the cell.
        If the cell is defined, the checksum is available, even if
        the value may not be.
        """
        hcell = self._get_hcell2()
        if self._get_hcell().get("UNTRANSLATED"):
            return hcell.get("checksum", {}).get("origin")
        ctx = self._get_context()
        if len(ctx.origin.inchannels):
            origin = ctx.origin
        else:
            origin = ctx.origin_integrated
        return origin.checksum

    @checksum.setter
    def checksum(self, checksum: Checksum | str):
        """Sets the checksum of the cell, as SHA3-256 hash"""
        checksum = Checksum(checksum)
        self.set_checksum(checksum)

    def set_checksum(self, checksum: Checksum):
        """Set the index checksum, i.e. the checksum of the deepcell dict"""
        checksum = Checksum(checksum)
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
        if not checksum:
            checksum = Checksum(empty_dict_checksum)
        origin_cell.set_auth_checksum(checksum)

    @property
    def keyorder(self):
        """Get the order of the keys of the deepcell.
        A custom keyorder can help in incremental computing."""
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
    def keyorder_checksum(self, checksum: Checksum):
        """Sets the keyorder checksum, as SHA3-256 hash"""
        self.set_keyorder_checksum(checksum)

    def set_keyorder_checksum(self, checksum: Checksum):
        """Sets the keyorder checksum, as SHA3-256 hash"""
        checksum = Checksum(checksum)
        hcell = self._get_hcell2()
        hcell.pop("metadata", None)
        checksum = Checksum(checksum).hex()
        if hcell.get("UNTRANSLATED"):
            if hcell.get("checksum") is None:
                hcell["checksum"] = {}
            hcell["checksum"]["keyorder"] = checksum
            return
        ctx = self._get_context()
        cell = ctx.keyorder
        if not checksum:
            checksum = Checksum(empty_list_checksum)
        cell.set_checksum(checksum)

    def define(self, distribution: dict):
        """Defines a DeepCell from a distribution
        A distribution is a dict containing at least "checksum" and "keyorder",
        which are Seamless checksums.
        Distribution metadata ("content_size", "index_size", "nkeys", "access_index")
        is stored as well, if available.
        """
        self.set_checksum(distribution["checksum"])
        self.set_keyorder_checksum(distribution["keyorder"])
        meta_keys = ["content_size", "index_size", "nkeys", "access_index"]
        try:
            distribution2 = None
            result = fair.find(distribution["checksum"])
            if result is not None:
                dataset, distribution2 = result["dataset"], result["distribution"]
            else:
                distribution2 = distribution
            if distribution2 is not None:
                metadata = {"dataset": dataset}
                for key in meta_keys:
                    if key in distribution2:
                        metadata[key] = distribution2[key]
                self._get_hcell()["metadata"] = metadata
        except Exception:
            pass

    @property
    def content_size(self):
        """The total size of all underlying buffers"""
        return self._get_hcell().get("metadata", {}).get("content_size")

    @property
    def index_size(self):
        """The size of the index, i.e. the buffer keys and their checksums"""
        index_size = self._get_hcell().get("metadata", {}).get("index_size")
        if index_size is None:
            try:
                ctx = self._get_context()
                cell = ctx.origin
                return len(cell._data.buffer)
            except Exception:
                return None
        return index_size

    @property
    def nkeys(self):
        """The number of buffer keys in the deepcell"""
        nkeys = self._get_hcell().get("metadata", {}).get("nkeys")
        if nkeys is None:
            try:
                ctx = self._get_context()
                cell = ctx.origin
                return len(cell.data)
            except Exception:
                return None
        return nkeys

    @property
    def filtered_checksum(self):
        """Contains the filtered checksum of the cell, as SHA3-256 hash.

        This is after blacklist/whitelist filtering has been applied
        """
        hcell = self._get_hcell2()
        if self._get_hcell().get("UNTRANSLATED"):
            return hcell.get("checksum", {}).get("filtered")
        ctx = self._get_context()
        return ctx.filtered0.checksum

    @property
    def filtered_keyorder(self):
        """Contains the filtered keyorder of the cell.

        This is after blacklist/whitelist filtering has been applied
        """
        _hcell = self._get_hcell2()
        if self._get_hcell().get("UNTRANSLATED"):
            raise AttributeError
        ctx = self._get_context()
        return ctx.filtered_keyorder.value

    @property
    def data(self):
        """Returns the data (checksum dict) of the deep cell"""
        ctx = self._get_context()
        cell = ctx.origin
        return deepcopy(cell.data)

    @property
    def _handle(self):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        ctx = self._get_context()
        cell = ctx.origin
        handle = cell.handle_hash
        return handle

    def set(self, value):
        """Sets the deep cell to a particular in-memory value
        Deep cell must have been translated first.
        """
        hcell = self._get_hcell()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError("Can set value only after translation")
        handle = self._handle
        handle.set(value)

    @property
    def status(self):
        """Returns the status of the deep cell.

        The status may be undefined, pending, error or OK
        If it is error, cell.exception will be non-empty.
        """
        if self._get_hcell().get("UNTRANSLATED"):
            return "Status: error (ctx needs translation)"
        ctx = self._get_context()
        for k in self._components:
            if k == "integrate_options" and not hasattr(ctx, k):
                continue
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

    def access(self, key):
        """Access the full value of an individual dict key.
        Use the FAIR server to download the value."""

        ctx = self._get_context()
        cell = ctx.origin
        data = cell.data
        checksum = data[key]
        if self.hash_pattern == {"*": "##"}:
            celltype = "bytes"
        else:
            celltype = "mixed"
        cs = Checksum(checksum)
        buf = fair.access(checksum, celltype, verbose=True)
        return deserialize(buf, cs, celltype, copy=False)

    @property
    def value(self):
        """Get a dict with each checksum expanded to its full value"""
        msg = """It is too costly to construct the full value of a deep cell
Use cell.data instead."""
        raise AttributeError(msg)

    @property
    def schema(self):
        """Deep cell schema"""
        raise AttributeError("Deep cell schemas are currently disabled.")

    def share(self, *, options: dict, path: str = None, toplevel=False):
        """TODO: document"""
        options2 = options
        for key, value in options.items():
            key = str(key)
            if not isinstance(value, dict):
                raise ValueError((key, value))
            if sorted(value.keys()) != ["checksum", "keyorder"]:
                raise ValueError("Wrong keys: {}".format((key, value)))
            value2 = {}
            for subkey, subvalue in value.items():
                try:
                    subvalue = Checksum(subvalue).hex()
                except ValueError:
                    raise ValueError((subkey, subvalue)) from None
                value2[subkey] = subvalue
            options2[key] = value2
        hcell = self._get_hcell()
        hcell["share"] = {"path": path, "options": options2}
        if toplevel:
            hcell["share"]["toplevel"] = True

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

    def _observe(self, key, checksum: Checksum):
        checksum = Checksum(checksum)
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
        if checksum:
            hcell["checksum"][key] = checksum

    def _set_observers(self):
        ctx = self._get_context()
        origin = ctx.origin.auth
        if origin is not None:
            origin._set_observer(partial(self._observe, "origin"))
        else:
            self._observe("origin", None)
        ctx.keyorder._set_observer(partial(self._observe, "keyorder"))
        ctx.filtered0._set_observer(partial(self._observe, "filtered"))
        ctx.blacklist._set_observer(partial(self._observe, "blacklist"))
        ctx.whitelist._set_observer(partial(self._observe, "whitelist"))

    def _get_subcell(self, attr):
        self._get_hcell()
        parent = self._parent()
        return DeepSubCell(parent, self, attr, readonly=False)

    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if hasattr(type(self), attr) or attr in self.__dict__ or attr == "path":
            return super().__getattribute__(attr)
        return self._get_subcell(attr)

    def __dir__(self):
        result = [p for p in type(self).__dict__ if not p.startswith("_")]
        return result

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
            assert (
                value._parent() is ctx
            )  # no connections between different (toplevel) contexts
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
        """The blacklist contains a list of keys that are filtered out when the deepcell is connected from"""
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError("Can set blacklist only after translation")
        return self._get_bwlist("blacklist")

    @blacklist.setter
    def blacklist(self, value):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        return self._set_bwlist("blacklist", value)

    @property
    def whitelist(self):
        """The blacklist contains a list of keys that are NOT filtered out when the deepcell is connected from"""
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError
        return self._get_bwlist("whitelist")

    @whitelist.setter
    def whitelist(self, value):
        hcell = self._get_hcell2()
        if hcell.get("UNTRANSLATED"):
            raise AttributeError("Can set whitelist only after translation")
        return self._set_bwlist("whitelist", value)

    def __getitem__(self, item):
        if isinstance(item, str):
            return self._get_subcell(item)
        else:
            raise TypeError(item)

    def __repr__(self):
        return str(self)


class DeepFolderCell(DeepCellBase):
    """Class for deep folder cells.
    Deep folder cells are cells whose value is a dict of checksums.
    The keys correspond to file names/paths."""

    _new_func = get_new_deepfoldercell
    hash_pattern = {"*": "##"}

    def __str__(self):
        return "Seamless DeepFolderCell: " + self.path

    @staticmethod
    def find_distribution(
        dataset: str,
        *,
        version: str = None,
        date: str = None,
        format: str = None,  # pylint: disable=redefined-builtin
        compression: str = None
    ):
        """Contact a FAIR server to find a distribution.
        The result is wrapped in a DeepFolderCell.

        "dataset", "version", "date", "format"  are arbitrary strings
        used to uniquely define the distribution.
        "compression" can be "gz", ..., or None.

        """
        distribution = fair.find_distribution(
            dataset,
            type="deepfolder",
            version=version,
            date=date,
            format=format,
            compression=compression,
        )
        ''' # disable for now, as it also gives access data
        print("""WARNING: finding a FAIR data distribution for a DeepFolderCell
is only weakly reproducible.
To guarantee strong reproducibility:
- Use "DeepFolderCell().define(DeepFolderCell.find_distribution(...))" only in IPython 
  and then use ctx.save().
OR: 
- If you prefer to use load_project.py:define_graph, enter the following code:

    distribution = {{
        "checksum": "{}",
        "keyorder": "{}",
    }}
    DeepFolderCell().define(distribution)
    
""".format(distribution["checksum"], distribution["keyorder"]))
        '''
        return distribution


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


class DeepCell(DeepCellBase):
    """Class for deep cells.
    Deep cells are cells whose value is a dict of checksums.
    The checksums correspond to "mixed" buffers, i.e.
    JSON and/or Numpy format."""

    _new_func = get_new_deepcell
    hash_pattern = {"*": "#"}

    def __str__(self):
        return "Seamless DeepCell: " + self.path

    @staticmethod
    def find_distribution(
        dataset: str,
        *,
        version: str = None,
        date: str = None,
        format: str = None,  # pylint: disable=redefined-builtin
        compression: str = None
    ):
        """Contact a FAIR server to find a distribution.
        The result is wrapped in a DeepCell.

        "dataset", "version", "date", "format"  are arbitrary strings
        used to uniquely define the distribution.
        "compression" can be "gz", ..., or None.

        """

        distribution = fair.find_distribution(
            dataset,
            type="deepcell",
            version=version,
            date=date,
            format=format,
            compression=compression,
        )
        ''' # disable for now, as it also gives access data
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
        '''
        return distribution


from .synth_context import SynthContext
from .SubCell import DeepSubCell
