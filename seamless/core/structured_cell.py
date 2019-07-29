from . import SeamlessBase
from .cell import PlainCell, TextCell
from .protocol import json_encode
from ..mixed import MixedBase, MonitorTypeError, Monitor, CellBackend
#from ..mixed.get_form import get_form
#from ..mixed.io.util import is_identical_debug

import weakref
import json
import traceback
import itertools
from copy import deepcopy

from .macro_mode import get_macro_mode

"""NOTE: data and schema can be edited via mount
If there is buffering, only the buffer should be edited via mount
"""
"""
        monitor = structured_cell.monitor
        if structured_cell._is_silk:
            handle = structured_cell._silk
            if structured_cell.buffer is not None:
                bufmonitor = structured_cell.bufmonitor
                assert isinstance(handle.data, MixedBase)
                bufmonitor.set_path(channel.inchannel, value, from_channel=True)
                handle.validate()
            else:
                try:
                    with handle.fork():
                        assert isinstance(handle.data, MixedBase)
                        monitor.set_path(channel.inchannel, value, from_channel=True)
                    monitor._update_outchannels(channel.inchannel)
                except Exception:
                    print("*** Error in setting channel %s ***" % channel)
                    traceback.print_exc()
                    print("******")
                    return False, False
"""

class PathDict(dict):
    def __getitem__(self, item):
        if isinstance(item, str):
            item = (item,)
        return super().__getitem__(item)

class Inchannel(SeamlessBase):
    def __init__(self, structured_cell, name):
        assert isinstance(name, tuple)
        self.structured_cell = weakref.ref(structured_cell)
        #assert all([isinstance(v, str) for v in channel])
        self.name = name
        super().__init__()

    @property
    def path(self):
        structured_cell = self.structured_cell()
        name = self.name
        if isinstance(name, str):
            name = (name,)
        if structured_cell is None:
            return ("<None>",) + name
        return structured_cell.path + name

    @property
    def status(self):
        """The cell's current status."""
        raise NotImplementedError ### cache branch

    @property
    def _context(self):
        return self.structured_cell().data._context

    @property
    def value(self):
        try:
            return self.structured_cell().monitor.get_data(self.inchannel)
        except MonitorTypeError:
            return None


class Outchannel(SeamlessBase):
    """
    Behaves like cells
    'worker_ref' actually is a reference to structured_cell
    """
    def __init__(self, structured_cell, name):
        assert isinstance(name, tuple)
        self.structured_cell = weakref.ref(structured_cell)
        #assert all([isinstance(v, str) for v in channel])
        self.name = name
        super().__init__()

    def connect(self, other):
        cell = self.structured_cell().data
        manager = self.structured_cell()._get_manager()
        manager.connect_cell(cell, other, self.name)

    @property
    def path(self):
        structured_cell = self.structured_cell()
        name = self.name
        if isinstance(name, str):
            name = (name,)
        if structured_cell is None:
            return ("<None>",) + name
        return structured_cell.path + name

    @property
    def status(self):
        """The cell's current status."""
        raise NotImplementedError ### cache branch

    @property
    def _context(self):
        return self.structured_cell().data._context

    @property
    def value(self):
        try:
            return self.structured_cell().monitor.get_data(self.outchannel)
        except MonitorTypeError:
            return None

class Editchannel(Outchannel):
    def __init__(self, structured_cell, name):
        raise NotImplementedError # livegraph branch
        # TODO: tricky, because of authority question; see LIVEGRAPH-TODO.txt
        assert isinstance(name, tuple)
        #assert all([isinstance(v, str) for v in channel])
        self.structured_cell = weakref.ref(structured_cell)
        self.name = name


class StructuredCell(SeamlessBase):
    _mount = None
    _exported = True
    _share_callback = None
    _celltype = "structured"
    _protected = False
    _rebind_schema = False
    def __init__(
      self,
      name,
      data,
      buffer,
      schema,
      inchannels,
      outchannels,
      *,
      editchannels=[],
    ):
        from .cell import MixedCell
        super().__init__()
        self.name = name
        
        assert isinstance(data, MixedCell)
        assert isinstance(buffer, MixedCell)
        self.data = data
        self.buffer = buffer

        if schema is None:
            self._is_silk = False
        else:
            assert isinstance(schema, PlainCell)
            self._is_silk = True
        self.schema = schema

        self.inchannels = PathDict()
        if inchannels is not None:
            for inchannel in inchannels:
                assert inchannel not in editchannels
                self.inchannels[inchannel] = Inchannel(self, inchannel)
        self.outchannels = PathDict()
        if outchannels is not None:
            for outchannel in outchannels:
                assert outchannel not in editchannels
                self.outchannels[outchannel] = Outchannel(self, outchannel)
        self.editchannels = PathDict()
        if editchannels is not None:
            for channel in editchannels:
                self.editchannels[channel] = Editchannel(self, channel)

        inedchannels = list(self.inchannels.keys())
        inedchannels += list(self.editchannels.keys())
        
        for path1 in inedchannels:
            lpath1 = len(path1)
            for path2 in inedchannels:                
                if path1 is path2:
                    continue
                if path2[:lpath1] == path1:
                    err = "%s and %s overlap"
                    raise Exception(err % (inedchannel1, inedchannel2))

        if self.data._monitor is None:
            backend = CellBackend(self.data)
            monitor = Monitor(backend)
            self.data._monitor = monitor

        if self._is_silk:
            assert self.data._silk is None
            bufmonitor = None
            if buffer is not None:
                bufmonitor = self.buffer._monitor                
                if bufmonitor is None:
                    bufbackend = CellBackend(self.buffer)
                    bufmonitor = Monitor(bufbackend)
                    self.buffer._monitor = bufmonitor            
            self._rebind(init=True)
        self._protected = True

    def _rebind(self, init=False):
        from ..silk import Silk
        from ..silk.Silk import SILK_NO_INFERENCE
        assert self.schema is not None
        if init:
            d = {}
            self.schema.set(d)
            self._schema_value = d
        else:
            self._schema_value = self.schema.value
        bufmonitor = None
        if self.buffer is not None:
            bufmonitor = self.buffer._monitor
        self._silk = Silk(
            schema=self._schema_value,
            schema_update_hook=self._update_schema,
            data=self.data._monitor,
            buffer=bufmonitor,
        )
        self._silk._modifier |= SILK_NO_INFERENCE
        self.data._silk = self._silk
        self._rebind_schema = False


    def __setattr__(self, attr, value):
        assert not self._destroyed
        if attr.startswith("_") or not self._protected:
            return super().__setattr__(attr, value)
        raise AttributeError("StructuredCell is protected; did you want to assign to .handle.%s instead?" % attr)    
        
    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        assert not self._destroyed
        return super().__getattribute__(attr)

    def _update_schema(self):
        self.schema.set(self._schema_value)

    def _set_observer(self, observer, trigger=True):
        self.data._set_observer(observer, trigger)

    def _add_traitlet(self, traitlet, trigger=True):
        self.data._add_traitlet(traitlet)

    def _set_context(self, context, name):
        from .manager import Manager
        from .unbound_context import UnboundContext, UnboundManager
        old_manager = None if self._context is None else self._get_manager()
        assert old_manager is None
        try:
            self._protected = False
            super()._set_context(context, name)
        finally:
            self._protected = True
        manager = self._get_manager()
        assert not ( (isinstance(manager, Manager) and isinstance(context, UnboundContext)) )
        manager.register_structured_cell(self)

    def _set_share_callback(self, sharefunc):
        return self.data._set_share_callback(sharefunc)

    @property
    def monitor(self):
        return self.data._monitor

    @property
    def checksum(self):
        return self.data.checksum
        
    def set(self, value):
        assert not self._destroyed
        if self._is_silk:
            if self._rebind_schema:
                self._rebind()
            self._silk.set(value)
        else:
            self.monitor.set_path((), value)


    def _set_checksum(self, checksum, *, initial, schema=False):
        assert not self._destroyed
        from .unbound_context import UnboundManager
        manager = self.data._get_manager()
        if schema:
            self.schema._set_checksum(checksum, initial=initial)
            self._rebind_schema = True
        else:
            if initial:
                self.buffer._set_checksum(checksum, initial=True)
            else:
                self.buffer._set_checksum(checksum, is_buffercell=True)

    def set_checksum(self, checksum):
        self._set_checksum(checksum)

    def __str__(self):
        ret = "Seamless structured cell: " + self._format_path()
        return ret

    @property
    def status(self):
        raise NotImplementedError # livegraph branch
        return self.data.status

    @property
    def value(self):
        """
        Returns the current value, as unbuffered Silk or dict
        Unless the schema has changed, this value always conforms
         to schema, even for buffered StructuredCells
        """
        from ..silk import Silk
        if self._is_silk:
            if self._rebind_schema:
                self._rebind()
            result = Silk(
                schema=self._schema_value,
                data=self.monitor.get_path()
            )
        else:
            result = self.monitor.get_data()
        return result

    @property
    def handle(self):
        """
        Returns handle for manipulation
        For buffered StructuredCells, its value may be against schema
        """
        if self._is_silk:
            if self._rebind_schema:
                self._rebind()
            result = self._silk
        else:
            monitor = self.monitor
            result = monitor.get_path()
        return result

    @property
    def example(self):
        """Returns example Silk structure, for schema definition"""
        assert not self._destroyed
        from ..silk import Silk
        assert self._is_silk
        if self._rebind_schema:
            self._rebind()
        return Silk(
            schema=self._silk.schema,
            schema_dummy=True
        )    
