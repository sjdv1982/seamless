import weakref
from copy import deepcopy
from . import SeamlessBase
from .status import StatusReasonEnum
from .utils import overlap_path

class Inchannel:
    _void = True
    _checksum = None
    _prelim = False
    _status_reason = StatusReasonEnum.UNDEFINED
    def __init__(self, structured_cell, subpath):
        assert isinstance(subpath, tuple)
        self.structured_cell = weakref.ref(structured_cell)
        self.subpath = subpath

    @property
    def hash_pattern(self):
        return self.structured_cell().hash_pattern

class Outchannel:
    def __init__(self, structured_cell, subpath):
        assert isinstance(subpath, tuple)
        self.structured_cell = weakref.ref(structured_cell)
        self.subpath = subpath
    def connect(self, target):
        sc = self.structured_cell()
        manager = sc._get_manager()
        if isinstance(target, Inchannel):
            target_subpath = target.subpath
            target = target.structured_cell().buffer
        else:
            target_subpath = None
        manager.connect(sc._data, self.subpath, target, target_subpath)

    @property
    def hash_pattern(self):
        return self.structured_cell().hash_pattern


class ModifiedPathManager:
    def __init__(self, structured_cell):
        self.structured_cell = weakref.ref(structured_cell)
        self.clear()

    def clear(self):
        self.modified_paths = set()       # just for bookkeeping
        self.modified_inchannels = set()  # for now, just for monitoring...
        self.modified_outchannels = set() # Used by join tasks

    def _add_path(self, path):
        if path in self.modified_paths:
            return
        for mp in self.modified_paths:
            if path[:len(mp)] == mp:
                return

        new_paths = set()
        new_paths.add(path)
        for mp in self.modified_paths:
            if mp[:len(path)] != path:
                new_paths.add(mp)
        self.modified_paths = new_paths

        if not len(self.modified_paths):
            return
        modified_outchannels = set()
        modified_outchannels.add( () )
        sc = self.structured_cell()
        if sc is None or sc._destroyed:
            return
        for outchannel in sc.outchannels:
            for mp in self.modified_paths:
                if overlap_path(outchannel, mp):
                    modified_outchannels.add(mp)
        modified_outchannels = set(modified_outchannels)
        if self.modified_outchannels != modified_outchannels:
            self.modified_outchannels = modified_outchannels

    def add_auth_path(self, path):
        self._add_path(path)

    def add_inchannel(self, inchannel):
        self.modified_inchannels.add(inchannel)
        self._add_path(inchannel)

class StructuredCell(SeamlessBase):
    _celltype = "structured"
    _exception = None
    _new_outgoing_connections = False
    def __init__(self, data, *,
        auth=None,
        schema=None,
        inchannels=[],
        outchannels=[],
        buffer=None,
        hash_pattern=None
    ):
        from .unbound_context import UnboundManager
        self.no_auth = False
        if auth is None:
            if not len(inchannels):
                if buffer is None:
                    auth = data
                else:
                    auth = buffer
            else:
                self.no_auth = True
        elif inchannels == [()]:
            auth = None
            self.no_auth = True

        if buffer is None and not len(inchannels):
            buffer = auth

        if schema is not None:
            assert buffer is not None and buffer is not data
        elif buffer is None:
            buffer = data

        assert isinstance(data, Cell)
        assert data._structured_cell is None
        assert data._celltype == "mixed"
        data._structured_cell = self
        self._data = data

        assert self.no_auth == (auth is None)
        if auth is not None:
            assert isinstance(auth, Cell)
            assert auth._celltype == "mixed"
            assert auth._structured_cell is None or auth._structured_cell is self
            auth._structured_cell = self
        self.auth = auth
        assert buffer is None or isinstance(buffer, Cell)
        if buffer is not None:
            assert buffer._celltype == "mixed"
            assert buffer._structured_cell is None or buffer._structured_cell is self
            buffer._structured_cell = self
        self.buffer = buffer
        assert schema is None or isinstance(schema, Cell)
        if schema is not None:
            assert schema._celltype == "plain"
        self.schema = schema

        assert data._hash_pattern == hash_pattern
        assert buffer._hash_pattern == data._hash_pattern
        if not self.no_auth:
            assert auth._hash_pattern == data._hash_pattern

        self._validate_channels(inchannels, outchannels)
        self.modified = ModifiedPathManager(self)

        self._auth_value = None
        self._schema_value = None

        if hash_pattern is not None:
            validate_hash_pattern(hash_pattern)
        self.hash_pattern = hash_pattern

    @property
    def exception(self):
        return self._exception

    @property
    def status(self):
        if self._exception is not None:
            return "Status: exception"
        return self._data.status

    def share(self, path, readonly=True, mimetype=None):
        assert readonly
        if path is None:
            path = ".".join(self.path)
        self._data.share(path, readonly=True, mimetype=mimetype)

    def _validate_channels(self, inchannels, outchannels):
        self.inchannels = PathDict()
        for inchannel in inchannels:
            self.inchannels[inchannel] = Inchannel(self, inchannel)
        self.outchannels = PathDict()
        for outchannel in outchannels:
            self.outchannels[outchannel] = Outchannel(self, outchannel)

        inchannels = list(self.inchannels.keys())

        for path1 in inchannels:
            lpath1 = len(path1)
            for path2 in inchannels:
                if path1 is path2:
                    continue
                lpath2 = len(path2)
                if path2[:lpath1] == path1 or path1[:lpath2] == path2:
                    err = "%s and %s overlap"
                    raise Exception(err % (path1, path2))

    def _get_auth_path(self, path):
        assert not self.no_auth, self
        assert self.auth is not None
        if self.auth._destroyed:
            return
        if self._auth_value is None:
            if self.auth._checksum is not None:
                self._auth_value = deepcopy(self.auth.value)
        manager = self._get_manager()
        if manager._destroyed:
            return
        return get_subpath(self._auth_value, self.hash_pattern, path)

    def set(self, value):
        self.handle.set(value)

    def set_no_inference(self, value):
        self.handle_no_inference.set(value)

    def _set_auth_path(self, path, value, from_pop=False, autogen=False):
        assert not self.no_auth
        if self.auth._destroyed:
            return
        self.modified.add_auth_path(path)
        manager = self._get_manager()
        if manager._destroyed:
            return
        resolve_cancel_cycle = False
        cancel_cycle = manager.cancel_cycle
        if not autogen:
            if cancel_cycle.cleared:
                resolve_cancel_cycle = True
                cancel_cycle.cleared = False
        try:
            if not from_pop and value is None and len(path) and isinstance(path[-1], int):
                l = len(self._get_auth_path(path[:-1]))
                tail = path[-1]
                new_value = None
                for n in range(l-1, path[-1]+1, -1):
                    path2 = path[:-1] + (n,)
                    old_value = self._get_auth_path(path2)
                    self._set_auth_path(path2, new_value, from_pop=True, autogen=True)
                    new_value = old_value
            elif self.hash_pattern is None:
                if not len(path):
                    self._auth_value = value
                elif self._auth_value is None:
                    if isinstance(path[0], str):
                        self._auth_value = {}
                    elif isinstance(path[0], list):
                        self._auth_value = []
                if len(path):
                    set_subpath(self._auth_value, None, path, value)
            else:
                if not isinstance(self._auth_value, (list, dict)):
                    if not len(path):
                        if list(self.hash_pattern.keys())[0][0] == "!":
                            self._auth_value = []
                        else:
                            self._auth_value = {}
                    else:
                        if isinstance(path[0], str):
                            self._auth_value = {}
                        elif isinstance(path[0], list):
                            self._auth_value = []
                set_subpath(self._auth_value, self.hash_pattern, path, value)
            cancel = True
            for inchannel in self.inchannels:
                if overlap_path(inchannel, path):
                    break
            else:
                cancel_cycle.cancel_scell_inpath(self, path, void=False, reason=None)
                self.auth._set_checksum(None, from_structured_cell=True)
        finally:
            if resolve_cancel_cycle:
                cancel_cycle.resolve()

    def _join(self):
        if self.buffer._destroyed:
            return
        manager = self._get_manager()
        if manager._destroyed:
            return
        manager.structured_cell_join(self)

    def _get_schema_path(self, path):
        if self.schema._destroyed:
            return
        manager = self._get_manager()
        if manager._destroyed:
            return
        return get_subpath(self._schema_value, None, path)

    def _set_schema_path(self, path, value):
        if self.schema._destroyed:
            return
        manager = self._get_manager()
        if manager._destroyed:
            return
        if not len(path):
            self._schema_value = value
        else:
            assert isinstance(path[0], str), path
            if self._schema_value is None:
                self._schema_value = {}
            set_subpath(self._schema_value, None, path, value)

    def _join_schema(self):
        if self.schema._destroyed:
            return
        buf = serialize(self._schema_value, "plain")
        checksum = calculate_checksum(buf)
        buffer_cache.cache_buffer(checksum, buf)
        if checksum is not None:
            checksum = checksum.hex()
        self.schema._set_checksum(checksum)#, from_structured_cell=True)
        manager = self._get_manager()
        manager.update_schemacell(
            self.schema,
            self._schema_value,
            self
        )
        manager.structured_cell_join(self)

    def _get_handle(self, inference):
        # Silk structure using self.auth
        # (_set_auth_path, _get_auth_path, wrapped in a Backend)
        # This is to control the authoritative part
        # If hash pattern, return the MixedDict/MixedList directly
        backend = StructuredCellBackend(self)
        monitor = Monitor(backend)
        mixed_object = MixedObject(monitor, ())
        schema = self.schema
        if schema is not None:
            schema_backend = StructuredCellSchemaBackend(self)
            schema_monitor = Monitor(schema_backend)
            schema = MixedDict(schema_monitor, ())
        if inference:
            default_policy = silk_default_policy
        else:
            default_policy = silk_no_infer_policy
        silk = Silk(
            data=mixed_object,
            schema=schema,
            default_policy=default_policy
        )
        return silk

    @property
    def handle(self):
        return self._get_handle(inference=True)

    @property
    def handle_no_inference(self):
        return self._get_handle(inference=False)

    @property
    def checksum(self):
        return self._data.checksum

    def set_checksum(self, checksum):
        return self._data.set_checksum(checksum)

    @property
    def value(self):
        # Silk structure using self._data.value
        # i.e. will always be a copy
        # i.e. modification is useless
        # i.e. any external modification to self._data will make it out-of-date
        # i.e. does NOT use the StructuredCellBackend, but DefaultBackend
        value = self._data.value
        schema = None
        if self.schema is not None:
            schema = self.schema.value
        return Silk(data=value, schema=schema)

    def get_schema(self):
        if self.schema is None:
            return None
        schema = self._schema_value
        if schema is None:
            if self.schema._checksum is not None:
                schema = self.schema.value
        return schema

    @property
    def data(self):
        """Raw mixed value (no Silk)"""
        return self._data.data

    def _set_context(self, context, name):
        from .unbound_context import UnboundManager
        has_ctx = self._context is not None
        super()._set_context(context, name)
        assert self._context() is context
        manager = self._get_manager()
        data_manager = self._data._get_manager()
        if not isinstance(manager, UnboundManager):
            if isinstance(data_manager, UnboundManager):
                data_manager = data_manager._ctx()._bound
        assert manager is data_manager, (manager, self._data._get_manager())
        if not has_ctx:
            manager.register_structured_cell(self)

    def destroy(self, *, from_del=False):
        if self._destroyed:
            return
        super().destroy(from_del=from_del)
        self._get_manager()._destroy_structured_cell(self)

    def has_authority(self, path=None):
        if path is not None: raise NotImplementedError
        return not self.no_auth

    def __str__(self):
        ret = "Seamless StructuredCell: " + self._format_path()
        return ret

class PathDict(dict):
    def __getitem__(self, item):
        if isinstance(item, str):
            item = (item,)
        return super().__getitem__(item)

from .cell import Cell
from .protocol.serialize import _serialize as serialize
from .protocol.calculate_checksum import calculate_checksum_sync as calculate_checksum
from .protocol.deep_structure import validate_hash_pattern
from .protocol.expression import get_subpath_sync as get_subpath, set_subpath_sync as set_subpath
from ..mixed.Monitor import Monitor
from ..mixed.Backend import StructuredCellBackend, StructuredCellSchemaBackend
from ..mixed import MixedObject, MixedDict
from ..silk.Silk import Silk
from ..silk.policy import (
    default_policy as silk_default_policy,
    no_infer_policy as silk_no_infer_policy
)
from .cache.buffer_cache import buffer_cache