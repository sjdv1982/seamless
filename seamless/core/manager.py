print("STUB: manager.py")

"""
All runtime access to cells and workers goes via the manager
also something like .touch(), .set().
Doing .set() on non-authoritative cells will result in a warning
Connecting to a cell with a value (making it non-authoritative), will likewise result in a warning
Cells can have only one outputpin writing to them, this is strictly enforced.

The manager has a notion of the managers of the subcontexts
The manager can maintain a value dict and an exception dict (in text form; the cells themselves hold the Python objects)
"""

class Manager:
    def __init__(self, ctx):
        self.ctx = ctx
        self.sub_managers = {}
        self.cell_to_pin = {}
        self._ids = 0
        self.unstable = set()

    def set_stable(self, worker, value):
        if value:
            self.unstable.remove(worker)
        else:
            self.unstable.add(worker)

    def get_id(self):
        self._ids += 1
        return self._ids

    def connect_cell(self, cell, target):
        assert isinstance(target, (InputPinBase, EditPinBase, Cell))
        if isinstance(target, ExportedInputPin):
            target = target.get_pin()

        if isinstance(target, Cell):
            raise NotImplementedError
            """
            self.add_cell_alias(source, target)
            target._on_connect(source, None, incoming = True)
            if source._status == Cell.StatusFlags.OK:
                value = source._data
                if source.dtype is not None and \
                  (source.dtype == "cson" or source.dtype[0] == "cson") and \
                  target.dtype is not None and \
                  (target.dtype == "json" or target.dtype[0] == "json"):
                    if isinstance(value, (str, bytes)):
                        value = cson2json(value)
                target._update(value,propagate=True)
            """
        worker = target.worker_ref()
        assert worker is not None #weakref may not be dead
        cell._check_mode(target.mode, target.submode)
        con_id = self.get_id()

        connection = (con_id, target)
        if cell._status == Cell.StatusFlags.OK:
            value = cell.serialize(target.mode, target.submode)
            target.receive_update(value)
        else:
            if isinstance(target, EditPinBase) and target.last_value is not None:
                raise NotImplementedError ### output *to* the cell!
                """
                self.update_from_worker(
                    self.get_cell_id(source),
                    target.last_value,
                    worker, preliminary=False
                )
                """

        if isinstance(target, EditPinBase):
            raise NotImplementedError ###


    def connect_pin(self, pin, target):
        raise NotImplementedError
        ###
        assert isinstance(target, CellLike) and target._like_cell
        if isinstance(target, Context):
            assert "_input" in target._pins
            target = target._pins["_input"]
        if isinstance(source, ExportedOutputPin):
            source = source.get_pin()
        worker = source.worker_ref()
        assert worker is not None #weakref may not be dead
        target._on_connect(source, worker, incoming = True)
        cell_id = self.get_cell_id(target)
        if cell_id not in self.cells:
            self.cells[cell_id] = target

        if cell_id not in source._cell_ids:
            source._cell_ids.append(cell_id)
            if con_id is None:
                self._connection_id()
            new_item = (weakref.ref(source), con_id)
            if target not in self.cell_to_output_pin:
                self.cell_to_output_pin[target] = [new_item]
            else:
                for itemnr, item in enumerate(
                  self.cell_to_output_pin[target]
                ):
                    if con_id > item[1]:
                        self.cell_to_output_pin[target].insert(
                            itemnr, new_item
                        )
                        break
                else:
                    self.cell_to_output_pin[target].append(new_item)

        if isinstance(worker, Transformer):
            worker._on_connect_output()
        elif source.last_value is not None:
            self.update_from_worker(
                cell_id,
                source.last_value,
                worker,
                preliminary=False
            )


    def set_cell(self, cell, value):
        assert isinstance(cell, Cell)
        cell.deserialize(value, "ref", None)

    def notify_attach_child(self, childname, child):
        if isinstance(child, Context):
            assert isinstance(child._manager, Manager)
            self.sub_managers[childname] = child._manager
        elif isinstance(child, Cell):
            if child._prelim_val:
                self.set_cell(child, child._prelim_val)
                child._prelim_val = None
        elif isinstance(child, Worker):
            child.activate()
        #then, trigger hook (not implemented)

from .context import Context
from .cell import Cell
from .worker import Worker, InputPin, EditPin, InputPinBase, EditPinBase, \
 ExportedInputPin, ExportedOutputPin
