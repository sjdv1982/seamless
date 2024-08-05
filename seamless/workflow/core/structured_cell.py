import weakref
from copy import deepcopy

from seamless import Checksum
from . import SeamlessBase
from .status import StatusReasonEnum
from .utils import overlap_path


class Inchannel:
    _void = True
    _checksum = None
    _prelim = False
    _status_reason = StatusReasonEnum.UNDEFINED
    _last_state = (None, None, None)  # Allows the inchannel state to be saved

    def __init__(self, structured_cell, subpath):
        assert isinstance(subpath, tuple)
        self.structured_cell = weakref.ref(structured_cell)
        self.subpath = subpath

    def _save_state(self):
        self._last_state = (self._void, self._checksum, self._status_reason)

    @property
    def exception(self):
        sc = self.structured_cell()
        livegraph = sc._get_manager().livegraph
        accessor = livegraph.paths_to_upstream[sc.buffer][self.subpath]
        if accessor is None:
            return None
        return accessor.exception

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


class StructuredCell(SeamlessBase):
    _celltype = "structured"
    _exception = None
    _mode = None  # SCModeEnum
    _cyclic = False  # the cell is part of a cyclic dependency. Don't forward inchannel cancels until it is resolved

    def __init__(
        self,
        data,
        *,
        auth=None,
        schema=None,
        inchannels=[],
        outchannels=[],
        buffer=None,
        hash_pattern=None,
        validate_inchannels=True
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

        self.inchannels = PathDict()
        for inchannel in inchannels:
            self.inchannels[inchannel] = Inchannel(self, inchannel)
        self.outchannels = PathDict()
        for outchannel in outchannels:
            self.outchannels[outchannel] = Outchannel(self, outchannel)
        if validate_inchannels:
            self._validate_inchannels()

        self._modified_auth = False
        self._auth_joining = False  #  an auth task is ongoing
        self._joining = False  #  a join task is ongoing

        self._auth_value = None  # obeys hash pattern
        self._auth_checksum = None  # obeys hash pattern
        self._auth_invalid = False
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

    def share(
        self, path, readonly=True, mimetype=None, *, toplevel=False, cellname=None
    ):
        if path is None:
            path = "/".join(self.path)
        self._data.share(
            path,
            readonly=readonly,
            mimetype=mimetype,
            toplevel=toplevel,
            cellname=cellname,
        )

    def _validate_inchannels(self):
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

    def _auth_none(self):
        assert not self.no_auth, self
        assert self.auth is not None
        if self.auth._destroyed:
            return
        if self._auth_value is None:
            return not Checksum(self.auth._checksum)
        return False

    def _get_auth_path(self, path):
        assert not self.no_auth, self
        assert self.auth is not None
        if self.auth._destroyed:
            return
        if self._auth_value is None:
            if Checksum(self.auth._checksum):
                self._auth_value = deepcopy(self.auth.data)
        manager = self._get_manager()
        if manager._destroyed:
            return
        return get_subpath(self._auth_value, self.hash_pattern, path)

    def set_buffer(self, buffer, checksum=None):
        from seamless import Buffer

        value = Buffer(buffer, checksum=checksum).deserialize("mixed")
        self.set_no_inference(value)

    def set(self, value):
        self.handle.set(value)

    def set_no_inference(self, value):
        self.handle_no_inference.set(value)

    def _set_auth_path(self, path, value, from_pop=False):
        assert not self.no_auth
        if self.auth._destroyed:
            return
        manager = self._get_manager()
        if manager._destroyed:
            return

        if self._auth_value is None:
            if self._auth_invalid and self._exception is not None:
                raise AttributeError(path)
            self._auth_value = deepcopy(
                self.auth.data
            )  # not .value, because of hash pattern

        if not from_pop and value is None and len(path) and isinstance(path[-1], int):
            l = len(self._get_auth_path(path[:-1]))
            tail = path[-1]
            new_value = None
            for n in range(l - 1, path[-1] + 1, -1):
                path2 = path[:-1] + (n,)
                old_value = self._get_auth_path(path2)
                self._set_auth_path(path2, new_value, from_pop=True)
                new_value = old_value
        else:
            if self.hash_pattern is None:
                if not len(path):
                    self._auth_value = deepcopy(value)
                elif self._auth_value is None:
                    if isinstance(path[0], str):
                        self._auth_value = {}
                    elif isinstance(path[0], list):
                        self._auth_value = []
            else:
                if not isinstance(self._auth_value, (list, dict)):
                    token = list(self.hash_pattern.keys())[0][0]
                    if token == "!":
                        self._auth_value = []
                    elif token == "*":
                        self._auth_value = {}
                    else:
                        raise NotImplementedError(self.hash_pattern)
            if len(path) or self.hash_pattern is not None:
                set_subpath(self._auth_value, self.hash_pattern, path, value)
            else:
                self._auth_value = deepcopy(value)
            self._join_auth()

    def _join_auth(self):
        from .manager.cancel import get_scell_state

        if self._destroyed:
            return
        if self.buffer._destroyed:
            return
        manager = self._get_manager()
        if manager._destroyed:
            return
        self.auth._set_checksum(None, from_structured_cell=True)
        self.auth._void = False
        self.auth._status_reason = None
        self._modified_auth = True
        if self.auth._observer is not None:
            self.auth._observer(None)
        if get_scell_state(self) == "void" and self._data is not self.auth:
            manager._set_cell_checksum(
                self._data, None, void=True, status_reason=StatusReasonEnum.UNDEFINED
            )
        manager.structured_cell_trigger(self)

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
                if Checksum(self.schema._checksum):
                    schema = self.schema.value
                    self._schema_value = schema
                else:
                    self._schema_value = {}
            set_subpath(self._schema_value, None, path, value)

    def _join_schema(self):
        """NOTE: This is an inefficient way of updating a schema value
        (re-calculate the checksum on every modification)

        But there shouldn't be any risk of data loss (no async operations)
        and schemas are small and rarely updated
        """
        from seamless import Buffer

        if self.schema._destroyed:
            return
        buf = Buffer(self._schema_value, "plain")
        checksum = buf.checksum
        checksum = Checksum(checksum)
        buffer_cache.cache_buffer(checksum, buf)
        buffer_cache.guarantee_buffer_info(checksum, "plain", sync_to_remote=False)
        self.schema._set_checksum(checksum, from_structured_cell=True)
        manager = self._get_manager()
        manager.update_schemacell(
            self.schema,
            self._schema_value,
        )

    def handle(self):
        return self._get_handle(inference=True)

    def _get_handle(self, inference):
        # Silk structure using self.auth
        # (_set_auth_path, _get_auth_path, wrapped in a Backend)
        # This is to control the authoritative part
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
        silk = Silk(data=mixed_object, schema=schema, default_policy=default_policy)
        return silk

    @property
    def handle(self):
        return self._get_handle(inference=True)

    @property
    def handle_no_inference(self):
        return self._get_handle(inference=False)

    @property
    def handle_hash(self):
        if self.hash_pattern is None:
            return self.handle
        backend = StructuredCellBackend(self)
        monitor = Monitor(backend)
        if self.hash_pattern in ({"*": "#"}, {"*": "##"}):
            mixed_object = MixedDict(monitor, ())
        elif self.hash_pattern == {"!": "#"}:
            mixed_object = MixedList(monitor, ())
        else:
            raise NotImplementedError(self.hash_pattern)
        return mixed_object

    @property
    def checksum(self):
        checksum = self._data.checksum
        checksum = Checksum(checksum)
        if checksum:
            return checksum
        if self.schema is None or not Checksum(self.schema.checksum):
            checksum = self.buffer.checksum
            checksum = Checksum(checksum)
            if checksum:
                return checksum
            if len(self.inchannels):
                return None
            return self.auth.checksum

    def set_auth_checksum(self, checksum: Checksum):
        checksum = Checksum(checksum)

        assert not self.no_auth
        self._auth_value = None
        self._auth_checksum = checksum
        self._join_auth()

    @property
    def value(self):
        # Silk structure using self._data.value
        # i.e. will always be a copy
        # i.e. modification is useless
        # i.e. any external modification to self._data will make it out-of-date
        # i.e. does NOT use the StructuredCellBackend, but DefaultBackend
        value = self._data.value
        schema = None
        schema = self.get_schema()
        return Silk(data=value, schema=schema)

    def get_schema(self):
        if self.schema is None:
            return None
        schema = self._schema_value
        if schema is None:
            if Checksum(self.schema._checksum):
                schema = self.schema.value
                self._schema_value = schema
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
        manager = self._get_manager()
        if not isinstance(manager, UnboundManager):
            manager._destroy_structured_cell(self)

    def has_independence(self, path=None):
        if path is not None:
            raise NotImplementedError
        return not self.no_auth

    def __str__(self):
        ret = "Seamless structured cell: " + self._format_path()
        return ret


class PathDict(dict):
    def __getitem__(self, item):
        if isinstance(item, str):
            item = (item,)
        return super().__getitem__(item)


from .cell import Cell
from .unbound_context import UnboundManager
from seamless.checksum.expression import validate_hash_pattern
from .protocol.expression import (
    get_subpath_sync as get_subpath,
    set_subpath_sync as set_subpath,
)
from silk.mixed.Monitor import Monitor
from silk.mixed.Backend import StructuredCellBackend, StructuredCellSchemaBackend
from silk.mixed import MixedObject, MixedDict, MixedList
from silk.Silk import Silk
from silk.policy import (
    default_policy as silk_default_policy,
    no_infer_policy as silk_no_infer_policy,
)
from seamless.checksum.buffer_cache import buffer_cache
