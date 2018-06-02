from .cell import CellLikeBase, Cell, JsonCell, TextCell
from ..mixed import MixedBase, OverlayMonitor
from .macro import get_macro_mode
from ..silk import Silk
import weakref
import traceback
from copy import deepcopy

class Inchannel(CellLikeBase):
    _authoritative = True
    _mount = None

    def __init__(self, structured_cell, inchannel):
        self.structured_cell = weakref.ref(structured_cell)
        self.inchannel = inchannel
        name = inchannel if inchannel != () else "self"
        self.name = name
        super().__init__()

    def _check_mode(self, mode, submode):
        if mode == "copy":
            print("TODO: Inchannel, copy data")
        if mode not in ("copy", None) or submode is not None:
            raise NotImplementedError

    def deserialize(self, value, mode, submode, *, from_pin, **kwargs):
        assert from_pin
        if value is None:
            self._status = self.StatusFlags.UNDEFINED
        else:
            self._status = self.StatusFlags.OK
        structured_cell = self.structured_cell()
        if structured_cell is None:
            return
        monitor = structured_cell.monitor
        if structured_cell._silk:
            handle = structured_cell.handle
            try:
                with handle.fork():
                    assert isinstance(handle.data, MixedBase)
                    monitor.set_path(self.inchannel, value, from_pin=True)
                monitor._update_outchannels(self.inchannel)
            except:
                traceback.print_exc(0)
                return False
        else:
            monitor.receive_inchannel_value(self.inchannel, value)
        different = True #TODO: keep checksum etc. to see if value really changed
        return different

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
        return self.structured_cell().monitor.get_data(self.inchannel)


class Outchannel(CellLikeBase):
    """
    Behaves like cells
    'worker_ref' actually is a reference to structured_cell
    """
    _mount = None
    mode = "copy"
    submode = None
    def __init__(self, structured_cell, outchannel):
        self.structured_cell = weakref.ref(structured_cell)
        self.outchannel = outchannel
        name = outchannel if outchannel != () else "self"
        self.name = name
        super().__init__()

    def _check_mode(self, mode, submode):
        if mode == "copy":
            print("TODO: Outchannel, copy data")
        if mode not in ("copy", "ref", None):
            raise NotImplementedError
        if submode not in ("silk", "json", None):
            raise NotImplementedError

    def serialize(self, mode, submode):
        structured_cell = self.structured_cell()
        assert structured_cell is not None
        data = structured_cell.monitor.get_data(self.outchannel)
        data = deepcopy(data) ###TODO: rethink a bit; note that deepcopy also casts data from Silk to dict!
        if submode == "silk":
            data = Silk(data=data)
        return data

    def deserialize(self, *args, **kwargs):
        return True #dummy

    def send_update(self, value):
        if value is None and self._status == self.StatusFlags.UNDEFINED:
           return
        if value is None:
            self._status = self.StatusFlags.UNDEFINED
        else:
            self._status = self.StatusFlags.OK
        structured_cell = self.structured_cell()
        assert structured_cell is not None
        data = structured_cell.data
        manager = data._get_manager()
        manager.set_cell(self, value)
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
        return self.structured_cell().monitor.get_data(self.outchannel)

class StructuredCell(CellLikeBase):
    _mount = None
    def __init__(
      self,
      name,
      data,
      storage,
      form,
      schema,
      inchannels,
      outchannels
    ):
        assert get_macro_mode()
        super().__init__()
        self.name = name

        assert isinstance(data, Cell)
        data._slave = True
        self.data = data
        if storage is None:
            assert isinstance(data, JsonCell)
            self._plain = True
        else:
            assert isinstance(storage, TextCell)
            storage._slave = True
            self._plain = False
        self.storage = storage

        assert isinstance(form, JsonCell)
        form._slave = True
        val = form._val
        assert val is None or isinstance(val, dict)
        self.form = form

        if schema is None:
            self._silk = False
        else:
            assert isinstance(schema, JsonCell)
            val = schema._val
            if val is None:
                manager = schema._get_manager()
                manager.set_cell(schema, {})
                val = schema._val
            assert isinstance(val, dict)
            self._silk = True
            schema._slave = True
        self.schema = schema

        self.inchannels = {}
        if inchannels is not None:
            for inchannel in inchannels:
                self.inchannels[inchannel] = Inchannel(self, inchannel)
        self.outchannels = {}
        if outchannels is not None:
            for outchannel in outchannels:
                self.outchannels[outchannel] = Outchannel(self, outchannel)

        monitor_data = self.data._val
        monitor_storage = self.storage._val if self.storage is not None else None
        monitor_form = self.form._val
        monitor_inchannels = list(self.inchannels.keys())
        monitor_outchannels = {ocname:oc.send_update for ocname, oc in self.outchannels.items()}
        data_hook = None
        if not isinstance(monitor_data, (list, dict)):
            data_hook = self._data_hook
        form_hook = None
        if not isinstance(monitor_form, (list, dict)):
            form_hook = self._form_hook
        storage_hook = None
        if not isinstance(monitor_storage, (list, dict)):
            storage_hook = self._storage_hook
        if self._silk:
            monitor_schema = self.schema._val
            monitor_data = Silk(monitor_schema,data=monitor_data)

        self.monitor = OverlayMonitor (
            data=monitor_data,
            storage=monitor_storage,
            form=monitor_form,
            inchannels=monitor_inchannels,
            outchannels=monitor_outchannels,
            plain=self._plain,
            data_hook=data_hook,
            form_hook=form_hook,
            storage_hook=storage_hook,
            attribute_access=self._silk,
        )

    def connect_inchannel(self, source, inchannel):
        ic = self.inchannels[inchannel]
        manager = source._get_manager()
        if isinstance(source, Cell):
            manager.connect_cell(source, ic)
        else:
            manager.connect_pin(source, ic)
        v = self.monitor.get_path(inchannel)
        status = ic.StatusFlags.OK if v is not None else ic.StatusFlags.UNDEFINED
        ic._status = status

    def connect_outchannel(self, outchannel, target):
        oc = self.outchannels[outchannel]
        manager = self.data._get_manager()
        manager.connect_cell(oc, target)
        v = self.monitor.get_path(outchannel)
        status = oc.StatusFlags.OK if v is not None else oc.StatusFlags.UNDEFINED
        oc._status = status

    def _data_hook(self, value):
        cell = self.data
        manager = cell._get_manager()
        manager.set_cell(cell, value, force=True)
        result = self.data._val
        if self._silk:
            monitor_schema = self.schema._val
            result = Silk(monitor_schema).set(result) #validates, infers schema, and wraps
        return result

    def _form_hook(self, value):
        cell = self.form
        manager = cell._get_manager()
        manager.set_cell(cell, value, force=True)
        return self.form._val

    def _storage_hook(self, value):
        cell = self.storage
        manager = cell._get_manager()
        manager.set_cell(cell, value, force=True)
        return self.storage._val

    def set(self, value):
        if self._silk:
            result = Silk(self.schema._val, data=self.handle)
            if isinstance(self.monitor.data, Silk):
                #Silk wrapping MixedObject wrapping Silk
                result._forks = self.monitor.data._forks
            result.set(value)
        else:
            self.monitor.set_path((), value)

    @property
    def value(self):
        result = self.monitor.get_data()
        return result

    @property
    def handle(self):
        result = self.monitor.get_path()
        if self._silk:
            result = Silk(self.schema._val, data=result)
            if isinstance(self.monitor.data, Silk):
                #Silk wrapping MixedObject wrapping Silk
                result._forks = self.monitor.data._forks
        return result


#TODO: schema could become not a slave
# but then, it may be updated from elsewhere; need to listen for that
#  and the schema may be connected to a target, which would require listening as well
