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
                except:
                    print("*** Error in setting channel %s ***" % channel)
                    traceback.print_exc()
                    print("******")
                    return False, False
"""

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
        assert isinstance(name, tuple)
        #assert all([isinstance(v, str) for v in channel])
        self.structured_cell = weakref.ref(structured_cell)
        self.name = name


class StructuredCell(SeamlessBase):
    _mount = None
    _exported = True
    _share_callback = None
    _celltype = "structured"
    def __init__(
      self,
      name,
      data,
      buffer,
      schema,
      plain,      
      inchannels,
      outchannels,
      *,
      editchannels=[],
    ):
        from ..silk import Silk
        from .cell import MixedCell
        super().__init__()
        self.name = name

        assert isinstance(data, MixedCell)
        self.data = data
        self._plain = plain

        if schema is None:
            self._is_silk = False
        else:
            assert isinstance(schema, PlainCell)
            self._is_silk = True
        self.schema = schema

        if buffer is not None:
            assert self._is_silk
            assert isinstance(buffer, MixedCell)
        self.buffer = buffer

        self.inchannels = {}
        if inchannels is not None:
            for inchannel in inchannels:
                assert inchannel not in editchannels
                self.inchannels[inchannel] = Inchannel(self, inchannel)
        self.outchannels = {}
        if outchannels is not None:
            for outchannel in outchannels:
                assert outchannel not in editchannels
                self.outchannels[outchannel] = Outchannel(self, outchannel)
        self.editchannels = {}
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

        self.backend = CellBackend(self.data)
        self.monitor = Monitor(self.backend, attribute_access=(not plain))

        if self._is_silk:
            self.schema_backend = CellBackend(self.schema)
            self.schema_monitor = Monitor(self.schema_backend, attribute_access=False)
            silk_buffer = None
            if buffer is not None:
                self.bufbackend = CellBackend(self.buffer)
                self.bufmonitor = Monitor(self.bufbackend, attribute_access=(not plain))
                silk_buffer = self.bufmonitor.get_path()
            self._silk = Silk(
                schema=self.schema_monitor,
                data=self.monitor.get_path(),
                buffer=silk_buffer,
            )

    def _set_context(self, context, name):
        from .manager import Manager
        from .unbound_context import UnboundContext, UnboundManager
        old_manager = None if self._context is None else self._get_manager()
        if old_manager is not None:
            assert isinstance(old_manager, UnboundManager)
        super()._set_context(context, name)
        manager = self._get_manager()
        assert not (isinstance(manager, Manager) and isinstance(context, UnboundContext))
        if old_manager is None:
            outedpaths = list(self.outchannels.keys()) + list(self.editchannels.keys())
            inpaths = [p for p in self.inchannels if p not in outedpaths]
            manager._register_cell_paths(self.data, inpaths, has_auth=False)
            manager._register_cell_paths(self.data, outedpaths, has_auth=True)

    def checksum(self):
        return self.data.checksum()

    def set(self, value):
        if self._is_silk:
            self._silk.set(value)
        else:
            self.monitor.set_path((), value)

    def __str__(self):
        ret = "Seamless structured cell: " + self._format_path()
        return ret

    @property
    def status(self):
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
            result = Silk(
                schema=self.schema._val,
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
            result = self._silk
        else:
            monitor = self.monitor
            result = monitor.get_path()
        return result


print("TODO: Runtime wrapper around StructuredCell that protects against .foo = bar\
 where .handle.foo = bar is intended")
