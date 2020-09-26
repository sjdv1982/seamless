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
import traceback


class StructuredCellCancellation:
    _inconsistent = False
    def __init__(self, scell, cycle):
        self.cycle = weakref.ref(cycle)
        self.scell = weakref.ref(scell)
        self.canceled_inchannels = {}
        self.canceled_outpaths = {}
        self.old_state = get_scell_state(scell)
        self.is_complex = scell_is_complex(scell)
        livegraph = cycle.manager().livegraph
        if not len(livegraph._destroying) and not scell._destroyed:
            state = get_scell_state(scell)
            self.is_void = (state == "void")
            try:
                assert self.is_void == scell._data._void, (scell,  scell._data._void, state, self.is_complex)
            except:
                self._inconsistent = True
                known_inconsistency = cycle._known_inconsistencies.get(scell.path)
                incon = (self.is_void, scell._data._void, state)
                if known_inconsistency is None or known_inconsistency != incon:
                    traceback.print_exc()
                    traceback.print_stack()
                    get_scell_state(scell, verbose=True)
                    cycle._known_inconsistencies[scell.path] = incon
            else:
                incon = cycle._known_inconsistencies.pop(scell.path, None)
        else:
            self.is_void = scell._data._void

    def cancel_inpath(self, inpath, void, reason):
        if self.is_complex:
            return
        if void and self.is_void:
            # no void cancellation will have any effect
            return
        scell = self.scell()
        if scell is None or scell._destroyed:
            return
        if inpath in scell.inchannels:
            self.canceled_inchannels[inpath] = (void, reason)
        cycle = self.cycle()
        for outpath in scell.outchannels:
            if void:
                if outpath in self.canceled_outpaths:
                    void0, reason0 = self.canceled_outpaths[outpath]
                    if (void0, reason0) == (void, reason):
                        continue
            else:
                if outpath in self.canceled_outpaths:
                    continue
                if not overlap_path(outpath, inpath):
                    continue
            self.canceled_outpaths[outpath] = (void, reason)
            cycle._cancel_cell_path(scell, outpath, void=void, reason=reason)

    def resolve(self, taskmanager, manager):
        if self._inconsistent:
            return

        scell = self.scell()

        if self.is_complex:
            if scell in self.cycle().complex_scell_to_resolve:
                return
            self.cycle().complex_scell_to_resolve.append(scell)
            return

        for path, (void, reason) in self.canceled_inchannels.items():
            ic = scell.inchannels[path]
            """
            if not void and ic._void:
                print("UNVOID!", scell, path)
            elif void and not ic._void:
                print("VOID!", scell, path)
            """
            if reason is None and void:
                reason = StatusReasonEnum.UPSTREAM
            manager._set_inchannel_checksum(
                ic, None, void, status_reason=reason,
                prelim=False, from_cancel_system=True
            )

        new_state = get_scell_state(scell)
        if new_state == "pending+":
            assert self.old_state == "pending+"
            return

        if new_state == "void":
            if not self.is_void:
                if scell._auth_invalid:
                    reason = StatusReasonEnum.INVALID
                else:
                    reason = scell._data._status_reason
                    if reason is None:
                        reason = StatusReasonEnum.UPSTREAM
                self.cycle().to_void[:] = [item for item in self.cycle().to_void if item[0] is not scell]
                self.cycle().to_void.append((scell, reason))
            return

        if new_state == "pending":
            if self.old_state == "pending":
                return
            #print("UNVOID FROM CANCEL", scell, "from", self.old_state)
            scell._equilibrated = False
            scell._exception = None
            scell._data._void = False

            if scell.auth is not None:
                scell.auth._void = False
            if scell.buffer is not None:
                scell.buffer._void = False
            return

        has_joins = len(taskmanager.structured_cell_to_task.get(scell, []))
        if new_state == "equilibrium":
            if self.old_state == "equilibrium":
                return
            if has_joins:
                return
            self.cycle().post_equilibrate.append(scell)
            return

        if new_state == "join":
            if not has_joins:
                manager.structured_cell_join(scell, False)
            return

        raise ValueError(new_state)


def revoid_worker(upstreams):
    for pinname, accessor in upstreams.items():
        if accessor is None:
            return StatusReasonEnum.UNCONNECTED
        if accessor._void:
            return StatusReasonEnum.UPSTREAM
    return None

from collections import deque

class CancellationCycle:
    """
    NOTE: all cancellation must happen within one async step
    Therefore, the direct or indirect call of _sync versions of coroutines
    (e.g. deserialize_sync, which launches coroutines and waits for them)
    IS NOT ALLOWED

    Calling back into the cancel system is OK after we clear the cycle, creating a nested resolve
    Calling the unvoid system is OK, although it may call back into the cancel system
    In both cases, the rule is: after clearing the cycle, in nested resolves, you can void but not unvoid
    Unvoiding, joining and complex structured cell updates are only done in the outer (unnested) resolve
    """
    cleared = False

    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.taskmanager = manager.taskmanager
        self._clear()
        self._known_inconsistencies = {}
        self.to_unvoid = deque()
        self.to_join = deque()
        self.complex_scell_to_resolve = deque()
        self.nested_resolve = 0
        self.origin_task = None

    def _clear(self):
        self.cells = {}  # => void, reason
        self.scells = {}  # StructuredCell => StructuredCellCancellation
        self.accessors = {}  # => void, reason
        self.transformers = {} # => void, reason
        self.reactors = {}  # => void, reason
        self.macros = {}  # => void, reason
        self.to_void = []
        self.macros_to_destroy = []
        self.post_equilibrate = []
        self.cleared = True


    def cancel_cell(self, cell, void, reason):
        if void and cell._void and reason == cell._status_reason:
            return
        assert not self.cleared

        if reason is None:
            reason = StatusReasonEnum.UPSTREAM

        if cell in self.cells:
            void0, reason0 = self.cells[cell]
            if not void or (void0, reason0) == (void, reason):
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
        if manager is None or manager._destroyed:
            return
        if void and cell._void:
            return
        taskmanager.cancel_cell(cell, origin_task=self.origin_task)
        if manager is None or manager._destroyed:
            return
        # use the _set_cell_checksum API, because we don't want to re-trigger a cancel cycle
        manager._set_cell_checksum(cell, None, void, status_reason=reason, unvoid=False) # no async, so OK

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

    def cancel_scell_inpath(self, scell, path, *, void, reason):
        assert not self.cleared
        if scell._destroyed:
            return
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)
        self.scells[scell].cancel_inpath(path, void, reason)

    def cancel_scell_post_join(self, scell):
        assert not self.cleared
        if scell._destroyed:
            return
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)

    def cancel_scell_soft(self, scell):
        for outchannel in scell.outchannels:
            self._cancel_cell_path(scell, outchannel, void=False, reason=None)

    def cancel_accessor(self, accessor, *, void, reason):
        if void and str(accessor).find("inp_PIN_write-autodock.py") > -1:
            #traceback.print_stack()
            pass
        if void:
            if accessor._void and accessor._status_reason == reason:
                return
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
        if manager is None or manager._destroyed:
            return
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
        if void and transformer._void and reason == transformer._status_reason:
            return
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
        if void and reactor._void and reason == reactor._status_reason:
            return
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
            editpins = [pinname for pinname in reactor._pins \
                if reactor._pins[pinname].io == "edit" ]
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
        try:
            self.nested_resolve += 1
            #print("CYCLE")
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

            to_void = self.to_void
            macros_to_destroy = self.macros_to_destroy
            post_equilibrate = self.post_equilibrate
            for ele, reason in to_void:
                if isinstance(ele, StructuredCell):
                    sc = ele
                    taskmanager.cancel_structured_cell(sc, kill_non_started=True, no_auth=True)
                    if sc.auth is not None and sc._auth_invalid:
                        manager._set_cell_checksum(sc.auth, None, True, reason)
                    if sc.buffer is not None:
                        manager._set_cell_checksum(sc.buffer, None, True, reason)
                    manager._set_cell_checksum(sc._data, None, True, reason)
                    sc._equilibrated = True
            self._clear()
            #print("/CYCLE")

            for scell in post_equilibrate:
                has_joins = len(taskmanager.structured_cell_to_task.get(scell, []))
                if has_joins:
                    continue
                downstreams = livegraph.paths_to_downstream[scell._data]
                for outpath in scell.outchannels:
                    for accessor in downstreams[outpath]:
                        if accessor._checksum is None:
                            accessor._soften = False
                            if len(taskmanager.accessor_to_task.get(accessor, [])): # running task
                                taskmanager.cancel_accessor(accessor, origin_task=self.origin_task)
                                AccessorUpdateTask(manager, accessor).launch()
                            else:
                                manager.cancel_accessor(accessor, void=True, origin_task=self.origin_task)

            for ele, reason in to_void:
                if isinstance(ele, StructuredCell):
                    sc = ele
                    manager.cancel_scell_hard(sc, reason)
                elif isinstance(ele, Transformer):
                    transformer = ele
                    upstreams = livegraph.transformer_to_upstream[transformer]
                    revoid_reason = revoid_worker(upstreams)
                    if revoid_reason:
                        manager.cancel_transformer(transformer, True, reason)
                elif isinstance(ele, Reactor):
                    reactor = ele
                    upstreams = livegraph.reactor_to_upstream[reactor]
                    revoid_reason = revoid_worker(upstreams)
                    if revoid_reason:
                        manager.cancel_reactor(reactor, True, reason)
                elif isinstance(ele, Macro):
                    macro = ele
                    upstreams = livegraph.macro_to_upstream[macro]
                    revoid_reason = revoid_worker(upstreams)
                    if revoid_reason:
                        manager.cancel_macro(ele, True, reason)
                else:
                    raise TypeError(ele)


            for macro in macros_to_destroy:
                gen_context = macro._gen_context
                if gen_context is not None:
                    gen_context.destroy()
                    macro._gen_context = None
        finally:
            self.nested_resolve -= 1

        if self.nested_resolve > 0:
            return

        try:
            while len(self.complex_scell_to_resolve) or len(self.to_unvoid) or len(self.to_join):
                while len(self.complex_scell_to_resolve):
                    scell = self.complex_scell_to_resolve.popleft()
                    resolve_complex_scell(self, scell)
                while len(self.to_unvoid):
                    scell = self.to_unvoid.popleft()
                    if scell_is_complex(scell):
                        unvoid_complex_scell(self, scell)
                    else:
                        manager.cancel_scell_soft(scell)
                while len(self.to_join):
                    scell = self.to_join.popleft()
                    scell._exception = None
                    manager.structured_cell_join(scell, False)
        finally:
            self.origin_task = None

        #print("/CYCLE2")

from ..utils import overlap_path
from ..manager.accessor import Accessor
from ..cell import Cell
from ..worker import Worker
from ..transformer import Transformer
from ..macro import Macro, Path
from ..reactor import Reactor
from ..status import StatusReasonEnum
from ..structured_cell import StructuredCell
from ..manager.tasks.accessor_update import AccessorUpdateTask
from .tasks.structured_cell import StructuredCellJoinTask
from .complex_structured_cell import get_scell_state, scell_is_complex, resolve_complex_scell, unvoid_complex_scell