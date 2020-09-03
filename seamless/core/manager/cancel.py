import weakref

class StructuredCellCancellation:
    def __init__(self, scell, cycle):
        self.cycle = weakref.ref(cycle)
        self.scell = weakref.ref(scell)
        self.canceled_inchannels = {}
        self.canceled_outpaths = {}
        self.needs_join = False

    def cancel_inpath(self, inpath, void, reason):
        scell = self.scell()
        if scell is None or scell._destroyed:
            return
        self.needs_join = True
        if inpath in scell.inchannels:
            self.canceled_inchannels[inpath] = (void, reason)
        cycle = self.cycle()
        for outpath in scell.outchannels:
            if not overlap_path(outpath, inpath):
                continue
            if outpath in self.canceled_outpaths:
                void0, reason0 = self.canceled_outpaths[outpath]
                if not void or (void0, reason0) == (void, reason):
                    continue
            self.canceled_outpaths[outpath] = (void, reason)
            cycle._cancel_cell_path(scell, outpath, void=void, reason=reason)

    def cancel_all_outpaths(self, void, reason):
        scell = self.scell()
        if scell is None or scell._destroyed:
            return
        self.needs_join = True
        cycle = self.cycle()
        for outpath in scell.outchannels:
            if outpath in self.canceled_outpaths:
                void0, reason0 = self.canceled_outpaths[outpath]
                if not void or (void0, reason0) == (void, reason):
                    continue
            self.canceled_outpaths[outpath] = (void, reason)
            cycle._cancel_cell_path(scell, outpath, void=void, reason=reason)

    def cancel_outpath(self, outpath):
        scell = self.scell()
        if scell is None or scell._destroyed:
            return
        assert outpath == () or outpath in scell.outchannels, (outpath, scell.outchannels)
        void = True
        reason = StatusReasonEnum.UPSTREAM
        if outpath in self.canceled_outpaths:
            void0, reason0 = self.canceled_outpaths[outpath]
            if not void or (void0, reason0) == (void, reason):
                return
        self.canceled_outpaths[outpath] = (void, reason)
        cycle = self.cycle()
        cycle._cancel_cell_path(scell, outpath, void=void, reason=reason)

    def resolve(self, taskmanager, manager):
        sc = self.scell()

        for path, (void, reason) in self.canceled_inchannels.items():
            if reason is None and void:
                reason = StatusReasonEnum.UPSTREAM
            ic = sc.inchannels[path]
            manager._set_inchannel_checksum(
                ic, None, void,
                status_reason=reason,
                from_cancel=True
            )

        clear_checksum = False
        void = False
        reason = None
        if () in self.canceled_outpaths:
            clear_checksum = True

        if self.needs_join:
            clear_checksum = True
            manager.structured_cell_join(sc, from_cancel=True)

        if clear_checksum and not self.needs_join:
            sc._data._set_checksum(None, from_structured_cell=True)


class CancellationCycle:
    """
    NOTE: all cancellation must happen with one async step
    Therefore, the direct or indirect call of _sync versions of coroutines
    (e.g. deserialize_sync, which launches coroutines and waits for them)
    IS NOT ALLOWED
    """
    cleared = False

    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.taskmanager = manager.taskmanager
        self._clear()

    def _clear(self):
        self.cells = {}  # => void, reason
        self.scells = {}  # StructuredCell => StructuredCellCancellation
        self.accessors = {}  # => void, reason
        self.transformers = {} # => void, reason
        self.reactors = {}  # => void, reason
        self.macros = {}  # => void, reason
        self.origin_task = None
        self.cleared = True

    def cancel_cell(self, cell, void, reason):
        assert not self.cleared

        if reason is None:
            reason = StatusReasonEnum.UPSTREAM

        if cell in self.cells:
            void0, reason0 = self.cells[cell]
            if not void or (void0, reason0) == (void, reason):
                return
        if not void and not cell._void and cell._checksum is None:
            return

        self.cells[cell] = (void, reason)

        manager = self.manager()
        livegraph = manager.livegraph
        accessors = livegraph.cell_to_downstream.get(cell, None)
        if accessors is None:
            if cell._destroyed:
                return
            raise KeyError(cell)
        for path in cell._paths:
            path_accessors = livegraph.macropath_to_downstream[path]
            accessors = accessors + path_accessors

        accessor_reason = StatusReasonEnum.UPSTREAM
        if void and reason == StatusReasonEnum.UNCONNECTED:
            accessor_reason = StatusReasonEnum.UNCONNECTED

        for accessor in accessors:
            self.cancel_accessor(
                accessor, void=void,
                reason=accessor_reason
            )

    def _resolve_cell(self, taskmanager, manager, cell, void, reason):
        if (not void) and cell._void:
            return
        taskmanager.cancel_cell(cell, origin_task=self.origin_task)
        if manager is None or manager._destroyed:
            return
        manager._set_cell_checksum(cell, None, void, status_reason=reason) # no async, so OK

    def _cancel_cell_path(self, scell, path, *, void, reason):
        assert not self.cleared
        cell = scell._data
        if cell._destroyed:
            return
        manager = self.manager()
        livegraph = manager.livegraph
        all_accessors = livegraph.paths_to_downstream.get(cell, None)
        if all_accessors is None:
            if cell._destroyed:
                return
            raise KeyError(cell)
        accessors = all_accessors[path]

        accessor_reason = StatusReasonEnum.UPSTREAM
        if void and reason == StatusReasonEnum.UNCONNECTED:
            accessor_reason = StatusReasonEnum.UNCONNECTED

        for accessor in accessors:
            self.cancel_accessor(
                accessor, void=void,
                reason=accessor_reason
            )

    def cancel_scell_inpath(self, scell, path, *, void, reason, from_join_task=False):
        assert not self.cleared
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)
        if not void and scell._exception is not None:
            return  # irrelevant; everything will be soft-canceled at resolve
        self.scells[scell].cancel_inpath(path, void, reason)
        if from_join_task:
            self.scells[scell].needs_join = False

    def cancel_scell_all_outpaths(self, scell, *, void, reason):
        assert not self.cleared
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)
        if not void and scell._exception is not None:
            return  # irrelevant; everything will be soft-canceled at resolve
        self.scells[scell].cancel_all_outpaths(void, reason)

    def cancel_scell_outpath(self, scell, path):
        """Hard-cancels an output path, because an scell has a value but the outpath has not"""
        assert not self.cleared
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)
        self.scells[scell].cancel_outpath(path)

    def cancel_accessor(self, accessor, *, void, reason):
        assert not self.cleared
        if accessor in self.accessors:
            void0, reason0 = self.accessors[accessor]
            if not void or (void0, reason0) == (void, reason):
                return

        self.accessors[accessor] = (void, reason)

        target = accessor.write_accessor.target()
        if isinstance(target, Path):
            target = target._cell
            if target is None:
                return

        if isinstance(target, Cell):
            if accessor.write_accessor.path is None:
                if target._structured_cell is not None:
                    assert target._structured_cell.schema is target, target # cancel_cell only on schema cells, else use cancel_scell_inpath
                return self.cancel_cell(target, void=void, reason=reason)
            else:
                assert target._structured_cell is not None
                self.cancel_scell_inpath(
                    target._structured_cell,
                    accessor.write_accessor.path,
                    void=void, reason=reason
                )
        elif isinstance(target, Worker):
            if isinstance(target, Transformer):
                return self.cancel_transformer(target, void=void, reason=reason)
            elif isinstance(target, Reactor):
                return self.cancel_reactor(target, void=void, reason=reason)
            elif isinstance(target, Macro):
                return self.cancel_macro(target, void=void, reason=reason)
            else:
                raise TypeError(target)
        else:
            raise TypeError(target)

    def _resolve_accessor(self, taskmanager, manager, accessor, void, reason):
        origin_task = self.origin_task
        taskmanager.cancel_accessor(accessor, origin_task=origin_task)
        if manager is None or manager._destroyed:
            return
        if origin_task is None \
          or not hasattr(origin_task, "accessor") \
          or origin_task.accessor is not accessor:
            if accessor.expression is not None:
                manager.livegraph.decref_expression(accessor.expression, accessor)
                accessor.expression = None
                accessor._checksum = None
        accessor._void = void

    def cancel_transformer(self, transformer, *, void, reason):
        assert not self.cleared
        if transformer in self.transformers:
            void0, reason0 = self.transformers[transformer]
            if not void or (void0, reason0) == (void, reason):
                return

        self.transformers[transformer] = (void, reason)

        manager = self.manager()
        livegraph = manager.livegraph

        downstreams = livegraph.transformer_to_downstream.get(transformer, None)
        if downstreams is None:
            if transformer._destroyed:
                return
            raise KeyError(transformer)
        for accessor in downstreams:
            self.cancel_accessor(
                accessor, void=void, reason=StatusReasonEnum.UPSTREAM
            )

    def _resolve_transformer(self, taskmanager, manager, transformer, void, reason):
        taskmanager.cancel_transformer(transformer)
        if manager is None or manager._destroyed:
            return
        if (not void) and transformer._void:
            return
        if void:
            assert reason is not None
            if transformer._void:
                curr_reason = transformer._status_reason
                if curr_reason.value < reason.value:
                    return
        manager._set_transformer_checksum(
            transformer, None, void,
            status_reason=reason,
            prelim = False
        )


    def cancel_reactor(self, reactor, *, void, reason):
        assert not self.cleared
        if reactor in self.reactors:
            void0, reason0 = self.reactors[reactor]
            if not void or (void0, reason0) == (void, reason):
                return

        self.reactors[reactor] = (void, reason)
        if void:
            outputpins = [pinname for pinname in reactor._pins \
                if reactor._pins[pinname].io == "output" ]
            manager = self.manager()
            livegraph = manager.livegraph
            downstreams = livegraph.reactor_to_downstream.get(reactor, None)
            if downstreams is None:
                if reactor._destroyed:
                    return
                raise KeyError(reactor)
            for pinname in outputpins:
                accessors = downstreams[pinname]
                for accessor in accessors:
                    self.cancel_accessor(accessor, void=True, reason=StatusReasonEnum.UPSTREAM)

    def _resolve_reactor(self, taskmanager, manager, reactor, void, reason):
        if manager is None or manager._destroyed:
            return
        if (not void) and reactor._void:
            return
        if reason is None:
            reason = StatusReasonEnum.UPSTREAM
        if void and reactor._void:
            curr_reason = reactor._status_reason
            if curr_reason.value < reason.value:
                return
        reactor._pending = (not void)
        reactor._void = void
        reactor._status_reason = reason

    def cancel_macro(self, macro, *, void, reason):
        assert not self.cleared
        if macro in self.macros:
            void0, reason0 = self.macros[macro]
            if not void or (void0, reason0) == (void, reason):
                return

        self.macros[macro] = (void, reason)

    def _resolve_macro(self, taskmanager, manager, macro, void, reason):
        if manager is None or manager._destroyed:
            return
        gen_context = macro._gen_context
        if void:
            if gen_context is not None:
                gen_context.destroy()
                macro._gen_context = None
            if macro._void:
                curr_reason = macro._status_reason
                if curr_reason.value < reason.value:
                    return
            macro._void = True
            macro._status_reason = reason

    def resolve(self):
        assert not self.cleared
        manager = self.manager()
        taskmanager = self.taskmanager
        for cell, (void, reason) in self.cells.items():
            self._resolve_cell(taskmanager, manager, cell, void, reason)
        for scell_cancellation in self.scells.values():
            scell_cancellation.resolve(taskmanager, manager)
        for accessor, (void, reason) in self.accessors.items():
            self._resolve_accessor(taskmanager, manager, accessor, void, reason)
        for transformer, (void, reason) in self.transformers.items():
            self._resolve_transformer(taskmanager, manager, transformer, void, reason)
        for reactor, (void, reason) in self.reactors.items():
            self._resolve_reactor(taskmanager, manager, reactor, void, reason)

        macros = list(self.macros.items())
        self._clear()
        for macro, (void, reason) in macros:
            self._resolve_macro(taskmanager, manager, macro, void, reason)

from ..utils import overlap_path
from ..cell import Cell
from ..worker import Worker
from ..transformer import Transformer
from ..macro import Macro, Path
from ..reactor import Reactor
from ..status import StatusReasonEnum
from ..structured_cell import StructuredCell
