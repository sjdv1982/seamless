import weakref

from . import SeamlessBase

class Inchannel:
    def __init__(self, structured_cell, name):
        assert isinstance(name, tuple)
        self.structured_cell = weakref.ref(structured_cell)
        self.name = name

class Outchannel:
    def __init__(self, structured_cell, name):
        assert isinstance(name, tuple)
        self.structured_cell = weakref.ref(structured_cell)
        self.name = name

class Editchannel:
    def __init__(self, structured_cell, name):
        assert isinstance(name, tuple)
        self.structured_cell = weakref.ref(structured_cell)
        self.name = name

"""
NOTE: the auth part of a StructuredCell is supposed to be small.
i.e.:
- It fits easily in memory (StructuredCell always keeps it in cache)
- Computing form and storage is quick (because it will be done often)
- Computing checksums is also fairly quick (which will be done after modification)
- No hash patterns! If you have an authoritative source for data that you want
  to encode with a deep structure, put it in a simple cell. Then, connect the simple
  cell as one of the inchannels (or the only inchannel). 
  Buffer and data cell can have the same hash pattern as the simple cell, and
   validation rules can be put in the schema.
"""

def set_subpath(curr_value, path, value):
    head = path[0]
    if len(path) == 1:
        curr_value[head] = value
        return
    if head not in curr_value:
        head2 = path[1]
        if isinstance(head2, int):
            curr_value[head] = []
        elif isinstance(head2, str):
            curr_value[head] = {}
    sub_curr_value = curr_value[head]
    set_subpath(sub_curr_value, path[1:], value)

def get_subpath(curr_value, path):
    if curr_value is None:
        return None
    if not len(path):
        return curr_value
    head = path[0]
    sub_curr_value = curr_value[head]
    return get_subpath(sub_curr_value, path[1:])

class StructuredCell(SeamlessBase):
    _celltype = "structured"    
    def __init__(self, data, *,
        auth=None,
        schema=None,
        inchannels=[],
        outchannels=[],
        editchannels=[],
        buffer=None
    ):      
        if len(inchannels):
            raise NotImplementedError # livegraph branch
        if len(editchannels):
            raise NotImplementedError # livegraph branch
        if len(outchannels):
            raise NotImplementedError # livegraph branch

        self.no_auth = False
        if auth is None:
            if not len(inchannels):
                if buffer is None:
                    auth = data            
                else:
                    auth = buffer
            else:
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

        if auth is not None:
            assert auth._hash_pattern is None
        assert buffer._hash_pattern == data._hash_pattern

        self._validate_channels(inchannels, outchannels, editchannels)
        self.modified_auth_paths = set()
        self.modified_schema = False

        self._auth_value = None
        self._schema_value = None


    def _validate_channels(self, inchannels, outchannels, editchannels):
        self.inchannels = PathDict()
        for inchannel in inchannels:
            self.inchannels[inchannel] = Inchannel(self, inchannel)
        self.outchannels = PathDict()
        for outchannel in outchannels:
            self.outchannels[outchannel] = Outchannel(self, outchannel)
        self.editchannels = PathDict()
        for editchannel in editchannels:
            self.editchannels[editchannel] = Editchannel(self, editchannel)

        inchannels = list(self.inchannels.keys()) + list(self.editchannels.keys())
        
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
        assert not self.no_auth
        if self.auth._destroyed:
            return
        manager = self._get_manager()
        if manager._destroyed:
            return
        return get_subpath(self._auth_value, path)

    def _set_auth_path(self, path, value):
        #print("_set_auth_path", path, value)
        assert not self.no_auth
        if self.auth._destroyed:
            return
        manager = self._get_manager()
        if manager._destroyed:
            return
        self.modified_auth_paths.add(path)
        manager.set_auth_path(self, path, value)
        if not len(path):
            self._auth_value = value
        else:
            if self._auth_value is None:
                if isinstance(path[0], str):
                    self._auth_value = {}
                elif isinstance(path[0], list):
                    self._auth_value = []
            set_subpath(self._auth_value, path, value)

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
        return get_subpath(self._schema_value, path)

    def _set_schema_path(self, path, value):
        if self.schema._destroyed:
            return
        manager = self._get_manager()
        if manager._destroyed:
            return
        self.modified_schema = True
        if not len(path):
            self._schema_value = value
        else:
            assert isinstance(path[0], str), path
            if self._schema_value is None:
                self._schema_value = {}
            set_subpath(self._schema_value, path, value)

    def _join_schema(self):
        if self.schema._destroyed:
            return
        buf = serialize(self._schema_value, "plain")
        checksum = calculate_checksum(buf)
        if checksum is not None:
            checksum = checksum.hex()
        self.schema._set_checksum(checksum, from_structured_cell=True)

    @property
    def handle(self):
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
        silk = Silk(data=mixed_object,schema=schema)
        return silk

    @property
    def value(self):
        # Silk structure using self._data.value 
        # i.e. will always be a copy
        # i.e. modification is useless        
        # i.e. any external modification to self._data will make it out-of-date
        # i.e. does NOT use the StructuredCellBackend, but DefaultBackend
        value = self._data.value
        schema = self._schema.value
        return Silk(data=data, schema=schema)

    @property
    def data(self):
        """Raw mixed value (no Silk)"""
        return self._data.data

    def _set_observer(self, observer, trigger=True):
        self._data._set_observer(observer, trigger)

    def _add_traitlet(self, traitlet, trigger=True):
        self._data._add_traitlet(traitlet)

    def _set_context(self, context, name):
        has_ctx = self._context is not None
        super()._set_context(context, name)
        assert self._context() is context
        manager = self._get_manager()
        assert manager is self._data._get_manager()
        if not has_ctx:
            manager.register_structured_cell(self)

    def destroy(self, *, from_del=False): 
        if self._destroyed:
            return
        super().destroy(from_del=from_del)        
        self._get_manager()._destroy_structured_cell(self)

    def __str__(self):
        ret = "Seamless StructuredCell: " + self._format_path()
        return ret

class PathDict(dict):
    def __getitem__(self, item):
        if isinstance(item, str):
            item = (item,)
        return super().__getitem__(item)

from .cell import Cell
from seamless.core.protocol.serialize import _serialize as serialize
from seamless.core.protocol.calculate_checksum import calculate_checksum_sync as calculate_checksum
from ..mixed.Monitor import Monitor
from ..mixed.Backend import StructuredCellBackend, StructuredCellSchemaBackend
from ..mixed import MixedObject, MixedDict
from ..silk.Silk import Silk