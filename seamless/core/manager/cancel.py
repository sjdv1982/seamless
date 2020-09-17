"""Canceling system

There are two canceling signals:
"void" means that an element is None and will remain None.
non-void means that the element is None but may be filled up later ("pending")

In a cancel cycle, the system records and propagates all signals internally,
unless a signal has already been received in this cycle.
Void overrides non-void.
The signals are then applied to the elements in the "resolve" stage of the cancel cycle.

- Simple cells and accessors are simple: they have at most one input and at most one output.
  Signals are simply propagated.

- Workers (transformers, reactors and macros) integrate multiple signals via their input pins.
  In the cancel cycle, signals are propagated eagerly to all output pin accessors.
  This always gives the correct result if at least one received signal is void.
  However, in case of a non-void signal, this is often over-eager, so the worker may have to be re-voided.

- Structured cells are complicated. During the resolve stage, it is decided to void/unvoid the structured cell
  and/or outchannel accessors based on inchannel and auth/schema modification state.
  It depends also if the cancel cycle was triggered by the join task of that structured cell, or not.
  It may also be decided that the structured cell is now in equilibrium, which
  means that outchannel accessors now have their final value: if they are None now, they will remain None.
  This undoes the accessor "void softening" that structured cell join tasks normally apply to outchannel accessors.
"""
import weakref

class StructuredCellCancellation:
    def __init__(self, scell, cycle):
        self.cycle = weakref.ref(cycle)
        self.scell = weakref.ref(scell)
        self.modified = scell._modified_auth or scell._modified_schema
        self.valid_inchannels = {k for k,ic in scell.inchannels.items() if not ic._void}
        self.pending_inchannels = {k for k,ic in scell.inchannels.items() if (ic._checksum is None and not ic._void) or ic._prelim}
        self.canceled_inchannels = {}
        self.canceled_outpaths = {}
        self.is_joined = False
        if cycle.origin_task is not None and isinstance(cycle.origin_task, StructuredCellJoinTask):
            if cycle.origin_task.structured_cell is scell:
                self.is_joined = True
        if self.is_joined:
            self.is_void = False
        else:
            if not len(_destroying) and not scell._destroyed:
                self.is_void = (not len(self.valid_inchannels)) and (not scell._modified_auth and not scell._modified_schema) and scell._data._checksum is None
                try:
                    assert self.is_void == scell._data._void, (scell, self.is_void, scell._modified_auth, scell._modified_schema, self.valid_inchannels, scell._data._void, scell._data._checksum is None)
                except:
                    import traceback; traceback.print_exc()
            else:
                self.is_void = scell._data._void

    def cancel_inpath(self, inpath, void, reason):
        scell = self.scell()
        if scell is None or scell._destroyed:
            return
        if inpath in scell.inchannels:
            self.canceled_inchannels[inpath] = (void, reason)
        cycle = self.cycle()
        for outpath in scell.outchannels:
            if void:
                if len(outpath) < len(inpath):
                    continue
                if outpath[:len(inpath)] != inpath:
                    continue
                if outpath in self.canceled_outpaths:
                    void0, reason0 = self.canceled_outpaths[outpath]
                    if (void0, reason0) == (void, reason):
                        continue
            else:
                if not overlap_path(outpath, inpath):
                    continue
                if outpath in self.canceled_outpaths:
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
        valid_inchannels = self.valid_inchannels.copy()

        for path, (void, reason) in self.canceled_inchannels.items():
            if void:
                pending_inchannels.discard(path)
                valid_inchannels.discard(path)
            else:
                valid_inchannels.discard(path)
                pending_inchannels.add(path)

        new_equilibrated = not len(pending_inchannels) # outchannels with value None become void
        if not self.is_joined:
            if sc._modified_auth or sc._modified_schema:
                new_equilibrated = False
        new_void = not len(valid_inchannels)

        if new_equilibrated and sc._exception is not None:
            new_void = True

        if not new_equilibrated:
            new_void = False

        if self.is_joined:
            # The cancel originated from a join task for this structured cell, and it's not a hard cancel
            assert not self.is_void
            reason = StatusReasonEnum.UPSTREAM
            if not self.cycle().origin_task.ok:
                if new_void:
                    # Set the structured cell to void.
                    if len(sc.inchannels):
                        reason = StatusReasonEnum.UPSTREAM
                    else:
                        reason = StatusReasonEnum.UNDEFINED
                    invalid = sc._exception is not None
                    if invalid:
                        reason = StatusReasonEnum.INVALID

                    taskmanager.cancel_structured_cell(
                        sc, kill_non_started=True,
                        no_auth=True,
                        origin_task=self.cycle().origin_task,
                    )
                    manager._set_cell_checksum(sc._data, None, void=True, status_reason=reason)
                    if sc.buffer is not sc.auth:
                        if sc.buffer._checksum is None:
                            manager._set_cell_checksum(sc.buffer, None, void=True, status_reason=reason)

        else:
            # The cancel did not originate from a join task for this structured cell
            assert self.modified == (sc._modified_auth or sc._modified_schema), sc
            if self.modified:
                new_void = False
            if new_void and not self.is_void:
                void_me = True
                new_equilibrated = False
            elif self.is_void and not new_void:
                unvoid_me = True
            if not new_void and not new_equilibrated:
                if sc._modified_auth or sc._modified_schema:
                    join_me = True
                else:
                    for k,ic in sc.inchannels.items():
                        if ic._checksum is not None:
                            join_me = True
                            break

        if new_equilibrated and not sc._equilibrated:
            sc._equilibrated = True
            taskmanager.cancel_structured_cell(
                sc, kill_non_started=True,
                no_auth=True,
                origin_task=self.cycle().origin_task
            )
            # Outchannel accessors that evaluate to None will now become void
            livegraph = manager.livegraph
            downstreams = livegraph.paths_to_downstream[sc._data]
            for outpath in sc.outchannels:
                for accessor in downstreams[outpath]:
                    accessor._soften = False
            if not self.is_joined or len(self.canceled_inchannels):  # joining task will have done this already, unless it is the
                self.cycle().post_equilibrate.append(sc)

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
            reason = sc._data._status_reason
            if reason is None:
                reason = StatusReasonEnum.UPSTREAM
            self.cycle().to_void.append((sc, reason))
        if join_me:
            self.cycle().to_join.append(sc)
        #print("CA", sc, unvoid_me, void_me, join_me, new_equilibrated, self.is_joined)


def revoid_worker(upstreams):
    for pinname, accessor in upstreams.items():
        if accessor is None:
            return StatusReasonEnum.UNCONNECTED
        if accessor._void:
            return StatusReasonEnum.UPSTREAM
    return None


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
        self.macros_to_destroy = []
        self.post_equilibrate = []
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
        # use the _set_cell_checksum API, because we don't want to re-trigger a cancel cycle
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
        if scell._destroyed:
            return
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)

    def cancel_scell_inpath(self, scell, path, *, void, reason):
        assert not self.cleared
        if scell._destroyed:
            return
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)
        self.scells[scell].cancel_inpath(path, void, reason)

    def cancel_scell_soft(self, scell):
        assert not self.cleared
        if scell._destroyed:
            return
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)
        self.scells[scell].cancel_all_outpaths(False, None)

    def cancel_scell_outpath_soft(self, scell):
        """Cancels an output path, because an scell has a value but the outpath has not"""
        assert not self.cleared
        if scell._destroyed:
            return
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
                accessor.clear_expression(manager.livegraph)
            accessor._checksum = None  #  accessors do not hold references to their checksums. Expressions do.
            accessor._void = void

    def cancel_transformer(self, transformer, *, void, reason):
        assert not self.cleared
        if transformer in self.transformers:
            void0, reason0 = self.transformers[transformer]
            if not void or (void0, reason0) == (void, reason):
                return

        manager = self.manager()
        livegraph = manager.livegraph

        downstreams = livegraph.transformer_to_downstream.get(transformer, None)

        if downstreams is None:
            if transformer._destroyed:
                return
            raise KeyError(transformer)

        if not void:
            upstreams = livegraph.transformer_to_upstream[transformer]
            if not len(downstreams):
                return
            for pinname, accessor in upstreams.items():
                if accessor is None: #unconnected
                    return

        self.transformers[transformer] = (void, reason)

        for accessor in downstreams:
            self.cancel_accessor(
                accessor, void=void, reason=StatusReasonEnum.UPSTREAM
            )

    def _resolve_transformer(self, taskmanager, manager, transformer, void, reason):
        if manager is None or manager._destroyed:
            return
        if void:
            assert reason is not None
            if transformer._void:
                curr_reason = transformer._status_reason
                if curr_reason.value <= reason.value:
                    return
        else:
            livegraph = manager.livegraph
            upstreams = livegraph.transformer_to_upstream[transformer]
            revoid_reason = revoid_worker(upstreams)
            if revoid_reason:
                self.to_void.append((transformer, revoid_reason))
                return

        void_error = (void == True) and (reason == StatusReasonEnum.ERROR)
        taskmanager.cancel_transformer(transformer)
        manager.cachemanager.transformation_cache.cancel_transformer(transformer, void_error)
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
        if reason is None:
            reason = StatusReasonEnum.UPSTREAM if void else None
        if void:
            assert reason is not None
            if reactor._void:
                curr_reason = reactor._status_reason
                if curr_reason.value < reason.value:
                    return
        else:
            livegraph = manager.livegraph
            upstreams = livegraph.reactor_to_upstream[reactor]
            revoid_reason = revoid_worker(upstreams)

            rtreactor = livegraph.rtreactors[reactor]
            editpin_to_cell = livegraph.editpin_to_cell[reactor]
            for pinname in editpins:
                if editpin_to_cell[pinname] is None:
                    revoid_reason = StatusReasonEnum.UNCONNECTED
                if editpin_to_cell[pinname]._void: # TODO: allow them to be void? By definition, these cells have authority
                    revoid_reason = StatusReasonEnum.UPSTREAM

            if revoid_reason:
                self.to_void.append((reactor, revoid_reason))
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
                self.macros_to_destroy.append(macro)
            if macro._void:
                curr_reason = macro._status_reason
                if curr_reason.value < reason.value:
                    return
            macro._void = True
            macro._status_reason = reason
        else:
            livegraph = manager.livegraph
            upstreams = livegraph.macro_to_upstream[macro]
            revoid_reason = revoid_worker(upstreams)
            if revoid_reason:
                self.to_void.append((macro, revoid_reason))
                return
            macro._void = False
            macro._status_reason = None

    def resolve(self):
        assert not self.cleared
        manager = self.manager()
        livegraph = manager.livegraph
        taskmanager = self.taskmanager

        for cell, (void, reason) in self.cells.items():
            self._resolve_cell(taskmanager, manager, cell, void, reason)
        for accessor, (void, reason) in self.accessors.items():
            # Accessors before scells and workers, so they can read their status
            self._resolve_accessor(taskmanager, manager, accessor, void, reason)

        # Structured cells and workers
        for scell_cancellation in self.scells.values():
            scell_cancellation.resolve(taskmanager, manager)
        for transformer, (void, reason) in self.transformers.items():
            self._resolve_transformer(taskmanager, manager, transformer, void, reason)
        for reactor, (void, reason) in self.reactors.items():
            self._resolve_reactor(taskmanager, manager, reactor, void, reason)
        for macro, (void, reason) in self.macros.items():
            self._resolve_macro(taskmanager, manager, macro, void, reason)

        to_void, to_unvoid, to_join = self.to_void, self.to_unvoid, self.to_join
        macros_to_destroy = self.macros_to_destroy
        post_equilibrate = self.post_equilibrate
        self._clear()

        for scell in post_equilibrate:
            downstreams = livegraph.paths_to_downstream[scell._data]
            taskmanager.cancel_structured_cell(
                scell, kill_non_started=True,
                no_auth=True
            ) # will cancel joins; will not cancel accessor updates
            for outpath in scell.outchannels:
                for accessor in downstreams[outpath]:
                    if accessor._checksum is None:
                        if len(taskmanager.accessor_to_task.get(accessor, [])):
                            manager.cancel_accessor(accessor, void=False, origin_task=self.origin_task)
                            AccessorUpdateTask(manager, accessor).launch()
                        else:
                            manager.cancel_accessor(accessor, void=True, origin_task=self.origin_task)
        for scell in to_unvoid:
            manager.unvoid_scell(scell)
        for scell in to_join:
            manager.structured_cell_join(scell, False)

        #print("/CYCLE")
        for ele, reason in to_void:
            if isinstance(ele, StructuredCell):
                sc = ele
                taskmanager.cancel_structured_cell(sc, kill_non_started=True, no_auth=True)
                if sc.auth is not None:
                    manager._set_cell_checksum(sc.auth, None, True, reason)
                if sc.buffer is not None:
                    manager._set_cell_checksum(sc.buffer, None, True, reason)
                manager._set_cell_checksum(sc._data, None, True, reason)
                sc._equilibrated = True
            elif isinstance(ele, Transformer):
                manager.cancel_transformer(ele, True, reason)
            elif isinstance(ele, Reactor):
                manager.cancel_reactor(ele, True, reason)
            elif isinstance(ele, Macro):
                manager.cancel_macro(ele, True, reason)
            else:
                raise TypeError(ele)


        for ele, reason in to_void:
            if isinstance(ele, StructuredCell):
                sc = ele
                manager.cancel_scell_hard(sc, reason)

        for macro in macros_to_destroy:
            gen_context = macro._gen_context
            gen_context.destroy()
            macro._gen_context = None


from ..utils import overlap_path
from ..cell import Cell
from ..worker import Worker
from ..transformer import Transformer
from ..macro import Macro, Path
from ..reactor import Reactor
from ..status import StatusReasonEnum
from ..structured_cell import StructuredCell
from ..manager.tasks.accessor_update import AccessorUpdateTask
from .tasks.structured_cell import StructuredCellJoinTask
from .. import _destroying