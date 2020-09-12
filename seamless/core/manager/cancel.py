import weakref

class StructuredCellCancellation:
    def __init__(self, scell, cycle):
        self.cycle = weakref.ref(cycle)
        self.scell = weakref.ref(scell)
        self.modified_auth = scell._modified_auth
        self.pending_inchannels = {k for k,ic in scell.inchannels.items() if ic._checksum is None and not ic._void}
        self.canceled_inchannels = {}
        self.canceled_outpaths = {}
        self.is_joined = False
        if cycle.origin_task is not None and isinstance(cycle.origin_task, StructuredCellJoinTask):
            if cycle.origin_task.structured_cell is scell:
                self.is_joined = True
        if self.is_joined:
            self.is_void = False
        else:
            self.is_void = (not len(self.pending_inchannels)) and (not scell._modified_auth) and scell._data._checksum is None
            assert self.is_void == scell._data._void, (scell, self.is_void, scell._modified_auth, self.pending_inchannels, scell._data._void, scell._data._checksum is None)

    def cancel_inpath(self, inpath, void, reason):
        scell = self.scell()
        if scell is None or scell._destroyed:
            return
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
        cycle = self.cycle()
        for outpath in scell.outchannels:
            if outpath in self.canceled_outpaths:
                void0, reason0 = self.canceled_outpaths[outpath]
                if not void or (void0, reason0) == (void, reason):
                    continue
            self.canceled_outpaths[outpath] = (void, reason)
            cycle._cancel_cell_path(scell, outpath, void=void, reason=reason)

    def cancel_outpath(self, outpath, void, reason=None):
        if reason is None:
            reason = StatusReasonEnum.UPSTREAM
        scell = self.scell()
        if scell is None or scell._destroyed:
            return
        assert outpath == () or outpath in scell.outchannels, (outpath, scell.outchannels)
        if outpath in self.canceled_outpaths:
            void0, reason0 = self.canceled_outpaths[outpath]
            if not void or (void0, reason0) == (void, reason):
                return
        self.canceled_outpaths[outpath] = (void, reason)
        cycle = self.cycle()
        cycle._cancel_cell_path(scell, outpath, void=void, reason=reason)

    def resolve(self, taskmanager, manager):
        unvoid_me = False
        void_me = False
        join_me = False

        sc = self.scell()
        pending_inchannels = self.pending_inchannels.copy()

        new_void = True
        for path, (void, reason) in self.canceled_inchannels.items():
            if void:
                pending_inchannels.discard(path)

        new_void = not len(pending_inchannels)

        for path, (void, reason) in self.canceled_inchannels.items():
            if not void:
                new_void = False

        void_cell = False
        if self.is_joined:
            # The cancel originated from a join task for this structured cell
            assert not self.is_void
            reason = StatusReasonEnum.UPSTREAM
            if not self.cycle().origin_task.ok:
                if new_void:
                    # Set the structured cell to void.
                    invalid = sc._exception is not None
                    if invalid:
                        reason = StatusReasonEnum.INVALID
                    manager._set_cell_checksum(sc._data, None, void=True, status_reason=reason)
                    if sc.buffer is not sc.auth:
                        if sc.buffer._checksum is None:
                            manager._set_cell_checksum(sc.buffer, None, void=True, status_reason=reason)
            if new_void:
                # Outchannel accessors that evaluate to None will now become void
                livegraph = manager.livegraph
                downstreams = livegraph.paths_to_downstream[sc._data]
                for outpath in sc.outchannels:
                    for accessor in downstreams[outpath]:
                        accessor._soften = False
        else:
            # The cancel did not originate from a join task for this structured cell
            assert self.modified_auth == sc._modified_auth, sc
            if self.modified_auth:
                new_void = False
            print("CANCEL NO JOIN", sc, new_void, self.is_void)
            if new_void and not self.is_void:
                void_me = True
            elif self.is_void and not new_void:
                unvoid_me = True
            if not new_void:
                if sc._modified_auth:
                    join_me = True
                else:
                    for k,ic in sc.inchannels.items():
                        if ic._checksum is not None:
                            join_me = True
                            break

        for path, (void, reason) in self.canceled_inchannels.items():
            if reason is None and void:
                reason = StatusReasonEnum.UPSTREAM
            ic = sc.inchannels[path]
            manager._set_inchannel_checksum(
                ic, None, void,
                status_reason=reason
            )

        if unvoid_me:
            self.cycle().to_unvoid.append(sc)
        elif void_me:
            self.cycle().to_void.append(sc)
        if join_me:
            self.cycle().to_join.append(sc)


class CancellationCycle:
    """
    NOTE: all cancellation must happen within one async step
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
        self.to_unvoid = []
        self.to_void = []
        self.to_join = []
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

    def cancel_scell_trigger(self, scell):
        """Consider a structured cell for canceling, without canceling specific inpaths or outpaths
        This will trigger a hard-cancel at resolve for previously soft-canceled paths,
         if the structured cell has no pending inchannels left
        """
        assert not self.cleared
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)

    def cancel_scell_inpath(self, scell, path, *, void, reason):
        assert not self.cleared
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)
        self.scells[scell].cancel_inpath(path, void, reason)

    def cancel_scell_soft(self, scell):
        assert not self.cleared
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)
        self.scells[scell].cancel_all_outpaths(False, None)

    def cancel_scell_outpath_soft(self, scell):
        """Cancels an output path, because an scell has a value but the outpath has not"""
        assert not self.cleared
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)
        self.scells[scell].cancel_outpath(path, False)

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
        if manager is None or manager._destroyed:
            return
        if (not void) and transformer._void:
            return
        if void:
            assert reason is not None
            if transformer._void:
                curr_reason = transformer._status_reason
                if curr_reason.value <= reason.value:
                    return
        taskmanager.cancel_transformer(transformer)
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
        self.to_unvoid = []
        self.to_void = []
        self.to_join = []
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

        to_void, to_unvoid, to_join = self.to_void, self.to_unvoid, self.to_join
        self._clear()

        macros = list(self.macros.items())
        for scell in to_unvoid:
            scell._unvoid()
        for scell in to_join:
            manager.structured_cell_join(scell)
        for scell in to_void:
            print("HARD CANCEL", scell)
            manager.cancel_scell_hard(scell)

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
from .tasks.structured_cell import StructuredCellJoinTask