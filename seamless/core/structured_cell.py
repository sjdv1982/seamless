from .cell import CellLikeBase, Cell, JsonCell, TextCell
from .protocol import json_encode
from ..mixed import MixedBase, OverlayMonitor, MakeParentMonitor, MonitorTypeError
from ..mixed.get_form import get_form
from ..mixed.io.util import is_identical_debug

import weakref
import json
import traceback
from copy import deepcopy
import threading, functools
from contextlib import contextmanager

from .macro_mode import get_macro_mode

"""NOTE: data and schema can be edited via mount
If there is buffering, only the buffer can be edit via mount
"""

"""
OverlayMonitor warns if an inchannel is overwritten via handle
 and again when the inchannel overwrites it back
But if the StructuredCell is buffered, this warning is lost
"""

#TODO: different supported_modes for inchannels and outchannels?
# (if yes, must also adapt editchannels two support two sets,
#   and teach manager._connect_cell_to_cell to pick the right set)
# Maybe YAGNI: with the text-json hack in channel_deserialize,
#  all seems to be working for now...

supported_modes_mixed = []
for transfer_mode in "copy", "ref":
    supported_modes_mixed.append((transfer_mode, "object", "mixed"))
supported_modes_mixed = tuple(supported_modes_mixed)
supported_modes_json = []
for transfer_mode in "copy", "ref":
    for access_mode in "json", "text", "object":
        if access_mode == "text" and transfer_mode == "ref":
            continue
        supported_modes_json.append((transfer_mode, access_mode, "json"))
supported_modes_json = tuple(supported_modes_json)

def channel_deserialize(channel, value, transfer_mode, access_mode, content_type,
 *, from_pin, **kwargs
):
    assert from_pin
    if value is None:
        channel._status = channel.StatusFlags.UNDEFINED
    else:
        channel._status = channel.StatusFlags.OK
        if access_mode == "text" and content_type == "json": #text-json hack
            value = json.loads(value)
            access_mode = "json"
        if access_mode == "object":
            assert content_type in ("json", "mixed"), (access_mode, content_type, value)
        else:
            assert access_mode in ("json", "mixed"), (access_mode, content_type, value)
    structured_cell = channel.structured_cell()
    if structured_cell is None:
        return
    with structured_cell._from_pin():
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
        else:
            monitor.receive_inchannel_value(channel.inchannel, value)
        dif = not is_identical_debug(value, channel._last_value)
        #TODO: keep checksum etc. to see if value really changed
        different, text_different = dif, dif
        channel._last_value = deepcopy(value)
    return different, text_different

class Inchannel(CellLikeBase):
    _authoritative = True
    _mount = None
    _last_value = None
    def __init__(self, structured_cell, inchannel):
        assert isinstance(inchannel, tuple)
        assert all([isinstance(v, str) for v in inchannel])
        self.structured_cell = weakref.ref(structured_cell)
        self.inchannel = inchannel
        name = inchannel
        self.name = name
        super().__init__()
        if structured_cell._plain:
            self._supported_modes = supported_modes_json
        else:
            self._supported_modes = supported_modes_mixed

    def deserialize(self, value, transfer_mode, access_mode, content_type,
     *, from_pin, **kwargs
    ):
        return channel_deserialize(
            self, value, transfer_mode, access_mode, content_type,
             from_pin=from_pin, **kwargs
        )

    @property
    def authoritative(self):
        return self._authoritative

    @property
    def path(self):
        structured_cell = self.structured_cell()
        name = self.name
        if isinstance(name, str):
            name = (name,)
        if structured_cell is None:
            return ("<None>",) + name
        return structured_cell.path + name

    def status(self):
        """The cell's current status."""
        return self._status.name

    @property
    def _context(self):
        return self.structured_cell().data._context

    @property
    def value(self):
        try:
            return self.structured_cell().monitor.get_data(self.inchannel)
        except MonitorTypeError:
            return None


class Outchannel(CellLikeBase):
    """
    Behaves like cells
    'worker_ref' actually is a reference to structured_cell
    """
    _mount = None
    _buffered = False
    _last_value = None ###TODO: use checksums; for now, only used for buffered
    def __init__(self, structured_cell, outchannel):
        assert isinstance(outchannel, tuple)
        assert all([isinstance(v, str) for v in outchannel])
        self.structured_cell = weakref.ref(structured_cell)
        self.outchannel = outchannel
        name = outchannel
        self.name = name
        super().__init__()
        if structured_cell.buffer is not None:
            self._buffered = True
        if structured_cell._plain:
            self._supported_modes = supported_modes_json
        else:
            self._supported_modes = supported_modes_mixed

    def checksum(self):
        return None #TODO
        # Easy enough for json, but needs access to form for mixed
        # (see MixedCell._checksum)

    def serialize(self, transfer_mode, access_mode, content_type):
        structured_cell = self.structured_cell()
        assert structured_cell is not None
        data = structured_cell.monitor.get_data(self.outchannel)
        if transfer_mode == "ref":
            result = data
        elif access_mode == "text":
            result = json_encode(data, sort_keys=True, indent=2)
        else:
            result = deepcopy(data)
        return result

    def deserialize(self, *args, **kwargs):
        raise Exception ###should never be called

    def send_update(self, value):
        if value is None and self._status == self.StatusFlags.UNDEFINED:
           return
        if value is None:
            self._status = self.StatusFlags.UNDEFINED
        else:
            self._status = self.StatusFlags.OK
        structured_cell = self.structured_cell()
        if is_identical_debug(value, self._last_value):
            return value
        self._last_value = deepcopy(value)
        assert structured_cell is not None
        data = structured_cell.data
        manager = data._get_manager()
        #print("set_cell", type(self).__name__, self.outchannel)
        manager.set_cell(self, value, origin=self)
        return value

    @property
    def path(self):
        structured_cell = self.structured_cell()
        name = self.name
        if isinstance(name, str):
            name = (name,)
        if structured_cell is None:
            return ("<None>",) + name
        return structured_cell.path + name

    def status(self):
        """The cell's current status."""
        return self._status.name

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
    _authoritative = True
    def __init__(self, structured_cell, channel):
        assert isinstance(channel, tuple)
        assert all([isinstance(v, str) for v in channel])
        self.structured_cell = weakref.ref(structured_cell)
        self.inchannel = channel
        self.outchannel = channel
        name = channel
        self.name = name
        CellLikeBase.__init__(self)
        if structured_cell.buffer is not None:
            self._buffered = True
        if structured_cell._plain:
            self._supported_modes = supported_modes_json
        else:
            self._supported_modes = supported_modes_mixed

    @property
    def authoritative(self):
        return self._authoritative

    def deserialize(self, value, transfer_mode, access_mode, content_type,
     *, from_pin, **kwargs
    ):
        return channel_deserialize(
            self, value, transfer_mode, access_mode, content_type,
             from_pin=from_pin, **kwargs
        )

class BufferWrapper:
    def __init__(self, data, storage, form):
        self.data = data
        self.storage = storage
        self.form = form

def update_hook(cell):
    cell._reset_checksums()
    try:
        cell.touch()
        if cell._mount is not None:
            cell._get_manager().mountmanager.add_cell_update(cell)
    except AttributeError:
        pass

class StructuredCellState:
    data = None
    form = None
    storage = None
    schema = None
    buffer_data = None
    buffer_form = None
    buffer_storage = None
    buffer_nosync = False

    def set(self, sc, only_auth):
        assert isinstance(sc, StructuredCell)
        data_filtered = False
        store_buffer = False
        if only_auth:
            self.data, data_filtered = self._get_auth(sc, sc.data._val)
        else:
            self.data = deepcopy(sc.data._val)
        if sc.buffer is not None and sc._silk._buffer_nosync:
            self.buffer_nosync = True
            store_buffer = True #the buffer is out of sync
            data_filtered_buffer = data_filtered #store the auth part if data_filtered
            self.data = deepcopy(sc.data._val)
            data_filtered = False
        if data_filtered:
            storage, form = get_form(self.data)
        else:
            form = deepcopy(sc.form._val)
            storage = None
            if sc.storage is not None:
                storage = sc.storage._val
        self.form = form
        self.storage = storage
        if sc.schema is not None:
            self.schema = deepcopy(sc.schema._val)
        if store_buffer:
            if data_filtered_buffer:
                self.buffer_data, _ = self._get_auth(sc, sc.buffer.data._val)
                self.buffer_storage, self.buffer_form = get_form(self.buffer_data)
            else:
                self.buffer_data = deepcopy(sc.buffer.data._val)
                self.buffer_form = deepcopy(sc.buffer.form._val)
                self.buffer_storage = sc.buffer.storage._val
        return self

    def _get_auth(self, sc, data):
        # Returns:
        # - the authoritative part of the data
        # - Whether the data was filtered
        v = deepcopy(data)
        if not sc.inchannels:
            return v, False
        if list(sc.inchannels.keys()) == [()]:
            return None, False
        if v is None:
            return None, False
        assert isinstance(v, dict)
        for inchannel in sc.inchannels:
            vv = v
            for p in inchannel[:-1]:
                if not isinstance(vv, dict) or p not in vv:
                    vv = None
                    break
                vv = vv[p]
            p = inchannel[-1]
            if vv is not None and p in vv:
                vv.pop(p)
        return v, True

    def serialize(self):
        result = {}
        for k,v in self.__dict__.items():
            if v is not None:
                result[k] = deepcopy(v)
        return result

    @classmethod
    def from_data(cls, data):
        from ..silk import Silk
        if isinstance(data, Silk):
            data = data.self.data
        if isinstance(data, MixedBase):
            data = data.value
        storage, form = get_form(data)
        result = cls()
        result.storage = storage
        result.form = form
        result.schema = {}
        s = Silk(schema=result.schema).set(data)
        result.data = s.data
        return result

    def __deepcopy__(self, memo):
        result = StructuredCellState()
        result.data = deepcopy(self.data, memo)
        result.form = deepcopy(self.form, memo)
        result.storage = self.storage
        result.schema = deepcopy(self.schema, memo)
        result.buffer_data = deepcopy(self.buffer_data, memo)
        result.buffer_form = deepcopy(self.buffer_form, memo)
        result.buffer_storage = self.buffer_storage
        result.buffer_nosync = self.buffer_nosync
        return result


def set_state(cell, state):
    cell._val = state
    cell._reset_checksums()
    cell._status = cell.StatusFlags.OK
    cell.touch()

class StructuredCell(CellLikeBase):
    _mount = None
    _from_pin_mode = False
    _exported = True
    def __init__(
      self,
      name,
      data,
      storage,
      form,
      buffer,
      schema,
      inchannels,
      outchannels,
      *,
      editchannels=[],
      state=None #is used destructively, you may want to make a deepcopy beforehand
    ):
        from ..silk import Silk
        if not get_macro_mode():
            if not data._root()._direct_mode:
                raise Exception("This operation requires macro mode, since the toplevel context was constructed in macro mode")
        super().__init__()
        self.name = name

        assert isinstance(data, Cell)
        if state is not None and state.data is not None:
            set_state(data, deepcopy(state.data))
        assert data._master is None
        data._master = (self, "data")
        self.data = data
        if storage is None:
            assert isinstance(data, JsonCell)
            self._plain = True
        else:
            assert isinstance(storage, TextCell)
            if state is not None and state.storage is not None:
                storage._val = state.storage
                storage._reset_checksums()
                set_state(storage, deepcopy(state.storage))
            assert storage._master is None
            storage._master = (self, "storage")
            self._plain = False
        self.storage = storage

        assert isinstance(form, JsonCell)
        if state is not None and state.form is not None:
            set_state(form, deepcopy(state.form))
        assert form._master is None
        form._master = (self, "form")
        val = form._val
        #assert val is None or isinstance(val, dict), val
        self.form = form
        if schema is None:
            self._is_silk = False
        else:
            assert isinstance(schema, JsonCell)
            if state is not None and state.schema is not None:
                set_state(schema, deepcopy(state.schema))
            val = schema._val
            if val is None:
                manager = schema._get_manager()
                manager.set_cell(schema, {})
                val = schema._val
                assert isinstance(val, dict)
            assert isinstance(val, dict)
            self._is_silk = True
        self.schema = schema

        if buffer is not None:
            assert self._is_silk
            assert isinstance(buffer, BufferWrapper)
            if self._plain:
                assert isinstance(buffer.data, JsonCell)
                assert buffer.storage is None
            else:
                assert isinstance(buffer.storage, TextCell)
                assert buffer.storage._master is None
                buffer.storage._master = (self, "buffer_storage")
            if state is not None:
                if state.buffer_nosync:
                    if state.buffer_data is not None:
                        set_state(buffer.data, deepcopy(state.buffer_data))
                elif self.data._val is not None:
                    set_state(buffer.data, deepcopy(self.data._val))
            assert buffer.data._master is None
            buffer.data._master = (self, "buffer_data")
            if not self._plain:
                if state is not None:
                    if state.buffer_nosync:
                        if state.buffer_storage is not None:
                            set_state(buffer.storage, deepcopy(state.buffer_storage))
                    elif self.storage._val is not None:
                        set_state(buffer.storage, deepcopy(self.storage._val))
            assert isinstance(buffer.form, JsonCell)
            if state is not None:
                if state.buffer_nosync:
                    if state.buffer_form is not None:
                        set_state(buffer.form, deepcopy(state.buffer_form))
                elif self.form._val is not None:
                    set_state(buffer.form, deepcopy(self.form._val))
            assert buffer.form._master is None
            buffer.form._master = (self, "buffer_form")
        self.buffer = buffer

        self.inchannels = {}
        if inchannels is not None:
            for inchannel in inchannels:
                self.inchannels[inchannel] = Inchannel(self, inchannel)
        self.outchannels = {}
        if outchannels is not None:
            for outchannel in outchannels:
                self.outchannels[outchannel] = Outchannel(self, outchannel)
        self.editchannels = {}
        if editchannels is not None:
            for channel in editchannels:
                self.editchannels[channel] = Editchannel(self, channel)

        monitor_data = self.data._val
        assert not isinstance(monitor_data, MixedBase)
        monitor_storage = self.storage._val if self.storage is not None else None
        monitor_form = self.form._val
        monitor_inchannels = list(self.inchannels.keys())
        monitor_inchannels += list(self.editchannels.keys())
        monitor_editchannels = list(self.editchannels.keys())
        def double_update(func1, func2, *args, **kwargs):
            func1(*args, **kwargs)
            func2(*args, **kwargs)
        monitor_outchannels = {ocname:oc.send_update for ocname, oc in self.outchannels.items()}
        for cname, c in self.editchannels.items():
            func = self.editchannels[cname].send_update
            if cname in self.outchannels:
                func2 = self.outchannels[cname].send_update
                monitor_outchannels[cname] = functools.partial(double_update, func, func2)
            else:
                monitor_outchannels[cname] = func
        data_hook = self._data_hook
        form_hook = self._form_hook
        storage_hook = self._storage_hook
        data_update_hook = functools.partial(update_hook, self.data)
        form_update_hook = functools.partial(update_hook, self.form)

        self.monitor = OverlayMonitor(
            data=monitor_data,
            storage=monitor_storage,
            form=monitor_form,
            inchannels=monitor_inchannels,
            outchannels=monitor_outchannels,
            editchannels=monitor_editchannels,
            plain=self._plain,
            attribute_access=self._is_silk,
            data_hook=data_hook,
            form_hook=form_hook,
            storage_hook=storage_hook,
            data_update_hook=data_update_hook,
            form_update_hook=form_update_hook,
        )

        if self._is_silk:
            schema_update_hook = functools.partial(update_hook, self.schema)
            silk_buffer = None
            if buffer is not None:
                monitor_buffer_data = buffer.data._val
                monitor_buffer_storage = self.buffer.storage._val if self.buffer.storage is not None else None
                monitor_buffer_form = self.buffer.form._val
                buffer_data_hook = self._buffer_data_hook
                buffer_form_hook = self._buffer_form_hook
                buffer_storage_hook = self._buffer_storage_hook
                buffer_data_update_hook = functools.partial(update_hook, self.buffer.data)
                buffer_form_update_hook = functools.partial(update_hook, self.buffer.form)
                self.bufmonitor = MakeParentMonitor(
                  data=monitor_buffer_data,
                  storage=monitor_buffer_storage,
                  form=monitor_buffer_form,
                  plain=self._plain,
                  attribute_access=True,
                  data_hook=buffer_data_hook,
                  form_hook=buffer_form_hook,
                  storage_hook=buffer_storage_hook,
                  form_update_hook=buffer_form_update_hook,
                  data_update_hook=buffer_data_update_hook,
                )
                silk_buffer = self.bufmonitor.get_path()
            self._silk = Silk(
                schema=schema._val,
                data=self.monitor.get_path(),
                buffer=silk_buffer,
                stateful=True,
                schema_update_hook=schema_update_hook,
            )
        if self.buffer is not None:
            mountcell = self.buffer.data
            storagecell = self.buffer.storage
            formcell = self.buffer.form
        else:
            mountcell = self.data
            storagecell = self.storage
            formcell = self.form
        mountcell._mount_setter = self._set_from_mounted_file
        if storagecell is not None:
            storagecell._mount_setter = self._init_storage_from_mounted_file
            formcell._mount_setter = self._init_form_from_mounted_file
        if self.schema is not None:
            self.schema._mount_setter = self._set_schema_from_mounted_file
        if state is not None:
            self.touch()

    def _set_slave(self, mode, val):
        assert mode in ("data", "storage", "form", "schema", "buffer_data", "buffer_form", "buffer_storage")
        if mode == "data":
            self.data._val = val
            self.data._reset_checksums()
            self.monitor.data = val
        elif mode == "storage":
            self.storage._val = val
            self.storage._reset_checksums()
            self.monitor.storage = val
        elif mode == "form":
            self.form._val = val
            self.form._reset_checksums()
            self.monitor.form = val
        elif mode == "schema":
            self.schema.update(val)
        elif mode == "buffer_data":
            self.buffer.data._val = val
            self.buffer.data._reset_checksums()
            self.bufmonitor.data = val
        elif mode == "buffer_storage":
            self.buffer.storage._val = val
            self.bufmonitor.storage = val
        elif mode == "buffer_form":
            self.buffer_form._val = val
            self.buffer_form._reset_checksums()
            self.bufmonitor.form = val

    def touch(self):
        for outchannel in self.outchannels:
            oc = self.outchannels[outchannel]
            value = oc.value
            if value is not None:
                oc.send_update(value)
        for channel in self.editchannels:
            ec = self.editchannels[channel]
            value = ec.value
            if value is not None:
                ec.send_update(value)

    @property
    def authoritative(self):
        return not self.inchannels

    @property
    def has_authority(self):
        # Returns if the data contains any authoritative parts
        data = self.data._val
        if not self.inchannels:
            return True
        if list(self.inchannels.keys()) == [()]:
            return False
        if data is None:
            return False
        assert isinstance(data, dict), (data, self.inchannels)
        def _has_auth(v, path, inchannels):
            if not len(inchannels):
                return True
            for vv, vvalue in v.items():
                p = path + (vv,)
                if p in inchannels:
                    continue
                if not isinstance(vvalue, dict):
                    return True
                lp = len(p)
                inchannels2 = set([ic for ic in inchannels if ic[:lp] == p])
                if _has_auth(vv, p, inchannels2):
                    return True
            return False
        return _has_auth(self.data._val, (), self.inchannels)

    @contextmanager
    def _from_pin(self):
        old_from_pin_mode = self._from_pin_mode
        self._from_pin_mode = "edit"
        try:
            yield
        finally:
            self._from_pin_mode = old_from_pin_mode

    def connect_inchannel(self, source, inchannel, transfer_mode=None):
        ic = self.inchannels[inchannel]
        manager = source._get_manager()
        if isinstance(source, StructuredCell):
            source.connect_outchannel((), ic, transfer_mode=transfer_mode)
        elif isinstance(source, Cell):
            manager.connect_cell(source, ic, transfer_mode=transfer_mode)
        else:
            manager.connect_pin(source, ic)
        v = self.monitor.get_path(inchannel)
        status = ic.StatusFlags.OK if v is not None else ic.StatusFlags.UNDEFINED
        ic._status = status

    def connect_outchannel(self, outchannel, target, transfer_mode=transfer_mode):
        from ..mixed import MixedObject
        try:
            oc = self.outchannels[outchannel]
        except KeyError:
            oc = self.editchannels[outchannel]
        manager = self.data._get_manager()
        manager.connect_cell(oc, target, transfer_mode=transfer_mode)
        try:
            v = self.monitor.get_path(outchannel)
        except MonitorTypeError:
            v = None
        if isinstance(v, MixedObject):
            v = v.value
        status = oc.StatusFlags.OK if v is not None else oc.StatusFlags.UNDEFINED
        oc._status = status

    def connect_editchannel(self, editchannel, target, transfer_mode=transfer_mode):
        from ..mixed import MixedObject
        from .worker import EditPinBase
        ec = self.editchannels[editchannel]
        assert isinstance(target, (EditPinBase, Editchannel, Cell)), type(target)
        manager = self.data._get_manager()
        duplex = not isinstance(target, EditPinBase)
        manager.connect_cell(ec, target, duplex=duplex, transfer_mode=transfer_mode)
        try:
            v = self.monitor.get_path(editchannel)
        except MonitorTypeError:
            v = None
        if isinstance(v, MixedObject):
            v = v.value
        status = ec.StatusFlags.OK if v is not None else ec.StatusFlags.UNDEFINED
        ec._status = status

    def _data_hook(self, value):
        cell = self.data
        manager = cell._get_manager()
        manager.set_cell(cell, value, force=True, from_pin=self._from_pin_mode)
        result = self.data._val
        return result

    def _form_hook(self, value):
        cell = self.form
        manager = cell._get_manager()
        manager.set_cell(cell, value, force=True, from_pin=self._from_pin_mode)
        return self.form._val

    def _storage_hook(self, value):
        cell = self.storage
        manager = cell._get_manager()
        manager.set_cell(cell, value, force=True, from_pin=self._from_pin_mode)
        return self.storage._val

    def _buffer_data_hook(self, value):
        cell = self.buffer.data
        manager = cell._get_manager()
        manager.set_cell(cell, value, force=True, from_pin=self._from_pin_mode)
        result = self.buffer.data._val
        return result

    def _buffer_form_hook(self, value):
        cell = self.buffer.form
        manager = cell._get_manager()
        manager.set_cell(cell, value, force=True, from_pin=self._from_pin_mode)
        return self.buffer.form._val

    def _buffer_storage_hook(self, value):
        cell = self.buffer.storage
        manager = cell._get_manager()
        manager.set_cell(cell, value, force=True, from_pin=self._from_pin_mode)
        return self.buffer.storage._val

    def _init_storage_from_mounted_file(self, filebuffer, checksum):
        storage = filebuffer.strip("\n")
        assert storage in ("pure-plain", "pure-binary", "mixed-plain", "mixed-binary"), storage
        if self.buffer is not None:
            self.buffer.storage._val = storage
            self.buffer.storage._reset_checksums()
            self.bufmonitor.storage = storage
        else:
            self.storage._val = storage
            self.storage._reset_checksums()
            self.monitor.storage = storage

    def _init_form_from_mounted_file(self, filebuffer, checksum):
        form = json.loads(filebuffer)
        if self.buffer is not None:
            self.buffer.form._val = form
            self.buffer.form._reset_checksums()
            self.bufmonitor.form = form
        else:
            self.form._val = form
            self.form._reset_checksums()
            self.monitor.form = form
            cell = self.data

    def _set_from_mounted_file(self, filebuffer, checksum):
        cell = self.buffer.data if self.buffer is not None else self.data
        if threading.current_thread() != threading.main_thread():
            work = functools.partial(
              self._set_from_mounted_file,
              filebuffer=filebuffer, checksum=checksum
            )
            manager = cell._get_manager()
            manager.workqueue.append(work)
            return
        value = cell._from_buffer(filebuffer)
        self.set(value)

    def _set_schema_from_mounted_file(self, filebuffer, checksum):
        cell = self.schema
        if threading.current_thread() != threading.main_thread():
            work = functools.partial(
              self._set_schema_from_mounted_file,
              filebuffer=filebuffer, checksum=checksum
            )
            manager = cell._get_manager()
            manager.workqueue.append(work)
            return
        value = cell._from_buffer(filebuffer)
        cell._val.update(value)
        cell._reset_checksums()
        self._silk.validate(accept_none=True)


    def set(self, value):
        if self._is_silk:
            self._silk.set(value)
        else:
            self.monitor.set_path((), value)

    def __str__(self):
        ret = "Seamless structured cell: " + self._format_path()
        return ret

    def status(self):
        return self.data.status()

    @property
    def value(self):
        """
        Returns the current value, as unbuffered Silk or dict
        Unless the schema has changed, this value always conforms
         to schema, even for buffered StructuredCells
        """
        from ..silk import Silk
        schema_update_hook = functools.partial(update_hook, self.schema)
        if self._is_silk:
            result = Silk(
                schema=self.schema._val,
                data=self.monitor.get_path(),
                stateful=True,
                schema_update_hook=schema_update_hook,
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
