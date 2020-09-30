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

- Structured cells are complicated.
"""
import weakref
import traceback

from enum import Enum

SCModeEnum = Enum("SCModeEnum", (
    "VOID",
    "EQUILIBRIUM",
    "PENDING",
    "AUTH_JOINING",
    "JOINING",
    "FORCE_JOINING"
))

import logging
logger = logging.getLogger("seamless")

def print_info(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.info(msg)

def print_warning(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.warning(msg)

def print_debug(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.debug(msg)

def print_error(*args):
    msg = " ".join([str(arg) for arg in args])
    logger.error(msg)


def get_scell_state(scell, verbose=False):
    """Returns the state for a structured cell.

    Result:

    auth_joining:   An auth task is ongoing
    joining:   A join or auth task is ongoing
    void :     The structured cell and all outchannels must be voided
    pending:   Waiting for pending inchannels
               Everything must be unvoided, including scell value and exception
    devalued-: A join has happened earlier
               The scell is currently non-void.
               Some inchannels have been devalued (voided) since the last join
               A new join is needed.
               In the meantime, unvoid everything, including cell value and exception
    devalued+: A join has happened earlier.
               The scell is currently void, because of a schema exception.
               Some inchannels have been devalued (voided) since the last join
               A join is needed (where the schema might then unvoid the scell).
               In the meantime, unvoid everything, including scell value and exception
    equilibrium: nothing will change.
               The structured cell is not void. Some inchannels and outchannels are void, others not.
    join:      There are valid inchannels and/or an auth value.
               There are no pending inchannels or auth modifications, but no value has yet been set.
               (Or, the value was unset by a modified schema)
               Launch a join.
    """
    auth_joining = scell._auth_joining
    joining = scell._joining
    modified_auth = scell._modified_auth
    auth_invalid = scell._auth_invalid
    pending_inchannels = {k for k,ic in scell.inchannels.items() if (ic._checksum is None and not ic._void)}
    valid_inchannels = {k for k,ic in scell.inchannels.items() if not ic._void}
    devalued_inchannels = {k for k,ic in scell.inchannels.items() if (ic._void and ic._last_state[1] is not None)}
    has_auth = scell.auth is not None and scell.auth._checksum is not None
    has_exc = scell._exception is not None and not auth_invalid

    if auth_joining:
        result = "auth_joining"
    elif modified_auth:
        result = "pending"
    elif auth_invalid:
        result = "void"
    elif len(pending_inchannels):
        result = "pending"
    elif joining:
        result = "joining"
    elif not has_auth and not len(valid_inchannels):
        result = "void"
    else:
        if len(scell.inchannels):
            if has_exc:
                if len(devalued_inchannels):
                    result = "devalued+"
                else:
                    result = "void"
            else:
                if scell._data._checksum is None:
                    result = "join"
                else:
                    if len(devalued_inchannels):
                        result = "devalued-"
                    else:
                        result = "equilibrium"
        else: # implies has_auth
            if has_exc:
                result = "void"
            else:
                if scell._data._checksum is None:
                    result = "join"
                else:
                    result = "equilibrium"

    if verbose:
        print("STATE", scell, result, modified_auth, auth_invalid, pending_inchannels, valid_inchannels, devalued_inchannels, has_auth, has_exc)

    return result


class StructuredCellCancellation:
    _inconsistent = False
    def __init__(self, scell, cycle, trigger=False):
        self.cycle = weakref.ref(cycle)
        self.scell = weakref.ref(scell)
        self.state = get_scell_state(scell)
        self.mode = scell._mode
        if self.mode is None:
            self.mode = SCModeEnum.VOID
        self.has_propagated = False
        self.canceled_inchannels = {}
        livegraph = cycle.manager().livegraph
        if not len(livegraph._destroying) and not scell._destroyed and not scell._cyclic:
            try:
                assert (self.state == "void") == scell._data._void, (scell, scell._data._void, self.state)
            except:
                self._inconsistent = True
                known_inconsistency = cycle._known_inconsistencies.get(scell.path)
                incon = (self.state, scell._data._void)
                if known_inconsistency is None or known_inconsistency != incon:
                    traceback.print_exc()
                    traceback.print_stack()
                    get_scell_state(scell, verbose=True)
                    cycle._known_inconsistencies[scell.path] = incon
            else:
                incon = cycle._known_inconsistencies.pop(scell.path, None)

    def cancel_inpath(self, inpath, void, reason):
        scell = self.scell()
        if scell is None or scell._destroyed:
            return

        if inpath is not None:
            assert inpath in scell.inchannels, (scell, inpath)
            self.canceled_inchannels[inpath] = (void, reason)

        if void:
            return

        if inpath is not None:
            if self.mode not in (SCModeEnum.VOID, SCModeEnum.EQUILIBRIUM, SCModeEnum.JOINING):
                return
            if scell._cyclic:
                return
        if self.has_propagated:
            return
        self.has_propagated = True
        if self.mode == SCModeEnum.VOID:
            print_debug("***CANCEL***: will be unvoided %s" % scell)
        cycle = self.cycle()
        for outpath in scell.outchannels:
            cycle._cancel_cell_path(scell, outpath, void=void, reason=reason)

    def launch_auth_task(self, taskmanager):
        scell = self.scell()
        existing = False
        tasks = taskmanager.structured_cell_to_task[scell]
        for task in tasks:
            if isinstance(task, StructuredCellAuthTask):
                if not task._started:
                    existing = True
                    break
            task.cancel()
        if not existing:
            StructuredCellAuthTask(taskmanager.manager, scell).launch()
        scell._modified_auth = False
        scell._auth_joining = True
        scell._joining = False
        scell._mode = SCModeEnum.AUTH_JOINING
        self.mode = SCModeEnum.AUTH_JOINING

    def clear_sc_data(self):
        scell = self.scell()
        manager = self.cycle().manager()
        if scell._exception is not None:
            print_debug("***CANCEL***: cleared exception for %s" % scell)
            scell._exception = None
        if scell._data._void:
            print_debug("***CANCEL***: unvoided %s" % scell)
        elif scell._data._checksum is not None:
            print_debug("***CANCEL***: cleared %s" % scell)
        manager._set_cell_checksum(
            scell._data, None,
            void=False
        )
        if get_scell_state(scell) == "auth_joining":
            if scell.auth is not None:
                if scell.auth._void:
                    print_debug("***CANCEL***: unvoided auth %s" % scell)
                elif scell.auth._checksum is not None:
                    print_debug("***CANCEL***: cleared auth %s" % scell)
                manager._set_cell_checksum(
                    scell.auth, None,
                    void=False
                )
        if scell.buffer is not None:
            manager._set_cell_checksum(
                scell.buffer, None,
                void=False
            )


    def resolve(self, taskmanager, manager):
        if self._inconsistent:
            return

        scell = self.scell()
        if scell._mode is None:
            assert self.mode == SCModeEnum.VOID
        else:
            assert self.mode == scell._mode

        for path, (void, reason) in self.canceled_inchannels.items():
            ic = scell.inchannels[path]
            if not void and ic._void:
                print_debug("***CANCEL***: unvoided %s, inchannel %s" % (scell, path))
            elif void and not ic._void:
                print_debug("***CANCEL***: voided %s, inchannel %s" % (scell, path))
            if reason is None and void:
                reason = StatusReasonEnum.UPSTREAM
            manager._set_inchannel_checksum(
                ic, None, void, status_reason=reason,
                prelim=False, from_cancel_system=True
            )

        old_state = self.state
        new_state = get_scell_state(scell)

        was_auth_joining = scell._auth_joining
        if scell._modified_auth:
            self.clear_sc_data()
            self.launch_auth_task(taskmanager)

        #print("RESOLVE", scell, old_state, new_state, self.mode, scell._data._checksum is None)
        if new_state == "void":
            if self.mode == SCModeEnum.VOID:
                pass
            elif self.mode == SCModeEnum.AUTH_JOINING:
                assert scell.auth._checksum is None, (scell, old_state, new_state, self.mode)
                assert not scell.auth._void
                assert scell._auth_invalid
                print_debug("***CANCEL***: voided auth %s" % scell)
                scell.auth._void = True
                if scell._exception is not None:
                    reason = StatusReasonEnum.INVALID
                else:
                    reason = StatusReasonEnum.UNDEFINED
                self.cycle().to_void.append((scell, reason))
            elif self.mode in (SCModeEnum.JOINING, SCModeEnum.AUTH_JOINING, SCModeEnum.FORCE_JOINING):
                if self.mode != SCModeEnum.FORCE_JOINING:
                    # The join task went wrong
                    assert scell._data._checksum is None, (scell, old_state, new_state, self.mode)
                else:
                    # The forced join task might have gone wrong;
                    # or it succeeded, but later on, all valid inchannels were voided
                    pass
                if scell._exception is not None:
                    reason = StatusReasonEnum.INVALID
                else:
                    reason = StatusReasonEnum.UNDEFINED
                print_debug("***CANCEL***: marked for void %s (from joining)" % scell)
                self.cycle().to_void.append((scell, reason))
            elif self.mode == SCModeEnum.PENDING:
                # The last pending inchannel got void-canceled
                assert scell._data._checksum is None, (scell, old_state, new_state, self.mode)
                if scell._exception is not None:
                    reason = StatusReasonEnum.INVALID
                else:
                    reason = StatusReasonEnum.UNDEFINED
                print_debug("***CANCEL***: marked for void (from pending) %s" % scell)
                self.cycle().to_void.append((scell, reason))
            elif self.mode == SCModeEnum.EQUILIBRIUM:
                # The last valued inchannel got void-canceled
                assert scell._data._checksum is not None, (scell, old_state, new_state, self.mode)
                if scell._exception is not None:
                    reason = StatusReasonEnum.INVALID
                else:
                    reason = StatusReasonEnum.UNDEFINED
                print_debug("***CANCEL***: marked for void (from equilibrium) %s" % scell)
                self.cycle().to_void.append((scell, reason))
            else:
                raise ValueError((scell, old_state, new_state, self.mode))
            scell._mode = SCModeEnum.VOID
            return

        if new_state == "pending" and self.mode == SCModeEnum.FORCE_JOINING:
            # Special case; we have been in force join, so we are doing joins while we still have pending inchannels.
            # Don't go into pending
            return

        if new_state == "pending" and scell._cyclic:
            # Special case; we have been marked as part of a cyclic dependency (and previously had forced joins)
            # Don't go into pending until we are unmarked
            return

        if new_state == "joining":
            assert self.mode in (SCModeEnum.JOINING, SCModeEnum.FORCE_JOINING), (scell, old_state, new_state, self.mode)
            # Nothing to do; wait until the join task will finish, disable "joining", and trigger us
            return

        if new_state == "pending" or new_state == "auth_joining":
            if self.mode not in (SCModeEnum.PENDING, SCModeEnum.AUTH_JOINING):
                if self.mode == SCModeEnum.VOID:
                    self.cycle().to_unvoid.append(scell)
                elif self.mode == SCModeEnum.JOINING:
                    taskmanager.cancel_structured_cell(scell, no_auth=True)
                    scell._joining = False
                    self.clear_sc_data()
                else:
                    # if equilibrium: just clean
                    self.clear_sc_data()
                if not self.has_propagated:
                    self.cycle().to_cancel.append(scell)
                if new_state == "pending":
                    scell._mode = SCModeEnum.PENDING
                    # if new state is auth-joining, mode will have been set already
            elif self.mode == SCModeEnum.AUTH_JOINING or new_state == "auth_joining":
                if new_state == "pending":
                    scell._mode = SCModeEnum.PENDING
                if not was_auth_joining:
                    self.clear_sc_data()
                    if not self.has_propagated:
                        self.cycle().to_cancel.append(scell)
            else:
                assert self.mode == SCModeEnum.PENDING, (scell, old_state, new_state, self.mode)
                assert old_state == "pending", (scell, old_state, new_state, self.mode)
                if not self.has_propagated:
                    self.cycle().to_cancel.append(scell)
            return

        if new_state == "join":
            if old_state == "pending":
                # The last pending inchannel got void-canceled
                pass
            elif self.mode == SCModeEnum.EQUILIBRIUM:
                # or: the schema was modified
                assert scell._data._checksum is None, (scell, old_state, new_state, self.mode)
            else:
                # or: we were already in this state (probably a trigger cancel)
                assert old_state == "join", (scell, old_state, new_state, self.mode)
            if scell._mode is not None:   # or: if auth is set from initial translation
                if scell._cyclic and self.mode == SCModeEnum.VOID:
                    self.cycle().to_unvoid.append(scell)
                else:
                    assert self.mode in (SCModeEnum.PENDING, SCModeEnum.JOINING, SCModeEnum.AUTH_JOINING, SCModeEnum.EQUILIBRIUM, SCModeEnum.FORCE_JOINING), (old_state, new_state, scell._mode)
            taskmanager.cancel_structured_cell(scell, no_auth=True)
            scell._joining = True
            StructuredCellJoinTask(taskmanager.manager, scell).launch()
            scell._mode = SCModeEnum.JOINING
            return


        if new_state == "equilibrium":
            if self.mode == SCModeEnum.EQUILIBRIUM:
                pass
            elif self.mode in (SCModeEnum.JOINING, SCModeEnum.AUTH_JOINING):
                print_debug("***CANCEL***: in equilibrium: %s" % scell)
            elif self.mode == SCModeEnum.FORCE_JOINING:
                # We got finally rid of all pending inchannels. Do another join, hopefully the final one
                self.clear_sc_data()
                scell._joining = True
                StructuredCellJoinTask(taskmanager.manager, scell).launch()
                scell._mode = SCModeEnum.JOINING
                return
            elif self.mode == SCModeEnum.VOID:
                # Can't happen, because:
                # From void to equilibrium, you need to pass through X-joining
                raise ValueError((scell, old_state, new_state, self.mode))
            elif self.mode == SCModeEnum.PENDING:
                # Can't happen, because:
                # 1. In pending mode, _data._checksum must be None;
                # 2. In equilibrium mode, _data._checksum must not be None;
                # 3. Only join/auth tasks may set _data._checksum to not-None.
                if scell._data is scell.auth:
                    # Special case
                    pass
                else:
                    raise ValueError((scell, old_state, new_state, self.mode, scell._data._checksum is None))
            scell._mode = SCModeEnum.EQUILIBRIUM
            return

        if new_state == "devalued-":
            # Previous mode must be equilibrium, because:
            # 1. In pending mode and X-joining mode, _data._checksum must be None;
            # 2. The same is obviously the case for void
            # 3. Join/auth tasks will clear the devalued channels
            # HOWEVER, join/auth tasks will only clear at the end
            if self.mode != SCModeEnum.EQUILIBRIUM:
                raise ValueError((scell, old_state, new_state, self.mode, scell._data._checksum is None))
            taskmanager.cancel_structured_cell(scell, no_auth=True)
            scell._joining = True
            StructuredCellJoinTask(taskmanager.manager, scell).launch()
            scell._mode = SCModeEnum.JOINING
            return

        if new_state == "devalued+":
            # Previous mode must be void, because an exception must be present
            taskmanager.cancel_structured_cell(scell, no_auth=True)
            scell._joining = True
            StructuredCellJoinTask(taskmanager.manager, scell).launch()
            scell._mode = SCModeEnum.JOINING
            return

        raise ValueError(new_state)

def void_worker(upstreams):
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
    """
    cleared = False

    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.taskmanager = manager.taskmanager
        self._clear()
        self._known_inconsistencies = {}
        self.to_void = deque()
        self.to_unvoid = deque()
        self.to_cancel = deque()
        self.nested_resolve = 0
        self.origin_task = None
        self.cyclic_checksums = weakref.WeakKeyDictionary()

    def _clear(self):
        self.cells = {}  # => void, reason
        self.scells = {}  # StructuredCell => StructuredCellCancellation
        self.accessors = {}  # => void, reason
        self.workers = {} # => void, reason, fired_unvoid. Transformers and Reactors.
        self.macros = {}  # => void, reason
        self.macros_to_destroy = []
        self.cleared = True


    def cancel_cell(self, cell, void, reason):
        assert not self.cleared

        if not void and not cell._void and cell._checksum is None:
            return

        if reason is None:
            reason = StatusReasonEnum.UPSTREAM

        if cell in self.cells:
            void0, reason0 = self.cells[cell]
            if (void0, reason0) == (void, reason):
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
        if void and cell._void:
            if cell._status_reason == reason:
                return
        taskmanager.cancel_cell(cell, origin_task=self.origin_task)
        if void:
            print_debug("***CANCEL***: voided %s" % cell)
        else:
            if not cell._void and cell._checksum is None:
                return
            elif cell._void:
                print_debug("***CANCEL***: unvoided %s" % cell)
            else:
                print_debug("***CANCEL***: cleared %s" % cell)
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

    def cancel_scell_inpath(self, scell, path, *, void, reason):
        assert not self.cleared
        if scell._destroyed:
            return
        if scell not in self.scells:
            self.scells[scell] = StructuredCellCancellation(scell, self)
        self.scells[scell].cancel_inpath(path, void, reason)

    def trigger_scell(self, scell, *, update_schema=False, void=False):
        assert not self.cleared
        if scell._destroyed:
            return
        if void:
            if scell._mode == SCModeEnum.FORCE_JOINING:
                # To be expected... but we refuse to become void as long as we have pending inchannels
                pass
            else:
                assert not update_schema
                if not scell._data._void:
                    print_debug("***CANCEL***: voided %s" % scell)
                    manager = self.manager()
                    manager._set_cell_checksum(scell._data, None, void=True, status_reason=StatusReasonEnum.INVALID)
        else:
            if scell._data._void:
                if scell._modified_auth:
                    print_debug("***CANCEL***: unvoided %s" % scell)
                    manager = self.manager()
                    manager._set_cell_checksum(scell._data, None, void=False)
            elif update_schema and scell._data._checksum is not None:
                print_debug("***CANCEL***: cleared %s" % scell)
                manager = self.manager()
                manager._set_cell_checksum(scell._data, None, void=False)
            if scell not in self.scells:
                print_debug("***CANCEL***: trigger %s" % scell)
                self.scells[scell] = StructuredCellCancellation(scell, self)

    def cancel_accessor(self, accessor, *, void, reason):
        if void:
            if accessor._void and accessor._status_reason == reason:
                return
        else:
            if (not accessor._void) and accessor._checksum is None:
                if not accessor._new_macropath:
                    return
        assert not self.cleared
        if accessor in self.accessors:
            void0, reason0 = self.accessors[accessor]
            if (void0, reason0) == (void, reason):
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
            if isinstance(target, (Transformer, Reactor)):
                return self._cancel_worker(target, void=void, reason=reason)
            elif isinstance(target, Macro):
                return self.cancel_macro(target, void=void, reason=reason)
            else:
                raise TypeError(target)
        else:
            raise TypeError(target)

    def _resolve_accessor(self, taskmanager, manager, accessor, void, reason):
        origin_task = self.origin_task
        taskmanager.cancel_accessor(accessor, origin_task=origin_task)
        if accessor.expression is not None:
            accessor.clear_expression(manager.livegraph)
        accessor._checksum = None  #  accessors do not hold references to their checksums. Expressions do.
        accessor._void = void

    def _cancel_worker(self, worker, *, void, reason):
        # Always fire along void
        # Fire along unvoid only if the transformer is unvoid, and only once.
        assert not self.cleared
        if worker in self.workers:
            void0, reason0, fired_unvoid = self.workers[worker]
            if void and void0:
                return
            if not void and fired_unvoid:
                if void0:
                    self.workers[worker] = False, None, True
                return
        else:
            fired_unvoid = False

        manager = self.manager()
        livegraph = manager.livegraph

        if isinstance(worker, Transformer):
            downstreams = livegraph.transformer_to_downstream.get(worker, None)

            if downstreams is None:
                if worker._destroyed:
                    return
                raise KeyError(worker)

        else: # reactor

            outputpins = [pinname for pinname in worker._pins \
                if worker._pins[pinname].io == "output" ]

            downstreams = []
            all_downstreams = livegraph.reactor_to_downstream.get(worker, None)
            if downstreams is None:
                if worker._destroyed:
                    return
                raise KeyError(workwr)
            for pinname in outputpins:
                accessors = all_downstreams[pinname]
                downstreams += accessors

        fire = True
        if not void:
            fire = False
            if not worker._void:
                fired_unvoid = True
                fire = True
        if void:
            fired_unvoid = False
        self.workers[worker] = (void, reason, fired_unvoid)

        if fire:
            for accessor in downstreams:
                self.cancel_accessor(
                    accessor, void=void, reason=StatusReasonEnum.UPSTREAM
                )


    def cancel_transformer(self, transformer, *, void, reason):
        return self._cancel_worker(transformer, void=void, reason=reason)

    def cancel_reactor(self, reactor, *, void, reason):
        return self._cancel_worker(reactor, void=void, reason=reason)

    def _resolve_transformer(self, taskmanager, manager, transformer, void, reason, fired_unvoid):
        if void:
            assert reason is not None
            if transformer._void:
                if fired_unvoid:
                    print_debug("***CANCEL***: marked for re-void %s" % transformer)
                    self.to_void.append((transformer, reason))
                else:
                    curr_reason = transformer._status_reason
                    if curr_reason.value != reason.value:
                        transformer._status_reason = reason
                    return
            else:
                print_debug("***CANCEL***: voided %s" % transformer)
        else:
            if transformer._void:
                livegraph = manager.livegraph
                upstreams = livegraph.transformer_to_upstream[transformer]
                void_reason = void_worker(upstreams)
                if not void_reason:
                    self.to_unvoid.append(transformer)
                else:
                    transformer._status_reason = void_reason
                return
            else:
                if not fired_unvoid:
                    print_debug("***CANCEL***: marked for re-cancel %s" % transformer)
                    self.to_cancel.append(transformer)
                if transformer._checksum is not None:
                    print_debug("***CANCEL***: cleared %s" % transformer)


        void_error = (void == True) and (reason == StatusReasonEnum.ERROR)
        taskmanager.cancel_transformer(transformer)
        manager.cachemanager.transformation_cache.cancel_transformer(transformer, void_error)
        manager._set_transformer_checksum(
            transformer, None, void,
            status_reason=reason,
            prelim=False
        )



    def _resolve_reactor(self, taskmanager, manager, reactor, void, reason, fired_unvoid):
        if void:
            assert reason is not None
            if reactor._void:
                if fired_unvoid:
                    print_debug("***CANCEL***: marked for re-void %s" % reactor)
                    self.to_void.append((reactor, reason))
                else:
                    curr_reason = reactor._status_reason
                    if curr_reason.value != reason.value:
                        reactor._status_reason = reason
                    return
            else:
                print_debug("***CANCEL***: voided %s" % reactor)
        else:
            if reactor._void:
                livegraph = manager.livegraph
                upstreams = livegraph.reactor_to_upstream[reactor]
                void_reason = void_worker(upstreams)
                if not void_reason:
                    self.to_unvoid.append(reactor)
                else:
                    reactor._status_reason = void_reason
                return
            else:
                if not fired_unvoid:
                    print_debug("***CANCEL***: marked for re-cancel %s" % reactor)
                    self.to_cancel.append(reactor)
                    return


        reactor._pending = (not void)
        reactor._void = void
        reactor._status_reason = reason


    def cancel_macro(self, macro, *, void, reason):
        assert not self.cleared
        if macro in self.macros:
            void0, reason0 = self.macros[macro]
            if (void0, reason0) == (void, reason):
                return

        self.macros[macro] = (void, reason)

    def _resolve_macro(self, taskmanager, manager, macro, void, reason):
        gen_context = macro._gen_context
        taskmanager.cancel_macro(macro)
        if gen_context is not None:
            print_debug("***CANCEL***: marked for destruction %s" % macro)
            self.macros_to_destroy.append(macro)
        if void:
            if macro._void:
                curr_reason = macro._status_reason
                if curr_reason.value < reason.value:
                    return
            print_debug("***CANCEL***: voided %s" % macro)
            macro._void = True
            macro._status_reason = reason
        else:
            if macro._void:
                livegraph = manager.livegraph
                upstreams = livegraph.macro_to_upstream[macro]
                void_reason = void_worker(upstreams)
                if not void_reason:
                    self.to_unvoid.append(macro)
                else:
                    macro._status_reason = void_reason
                return

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
            for scell_cancellation in list(self.scells.values()):
                scell_cancellation.resolve(taskmanager, manager)
            for worker, (void, reason, fired_unvoid) in list(self.workers.items()):
                if isinstance(worker, Transformer):
                    self._resolve_transformer(taskmanager, manager, worker, void, reason, fired_unvoid )
                else:
                    self._resolve_reactor(taskmanager, manager, worker, void, reason, fired_unvoid)
            for macro, (void, reason) in list(self.macros.items()):
                self._resolve_macro(taskmanager, manager, macro, void, reason)
            self._clear()
            #print("/CYCLE")

            for macro in list(self.macros_to_destroy):
                gen_context = macro._gen_context
                if gen_context is not None:
                    print_debug("***CANCEL***: destroy %s" % macro)
                    gen_context.destroy()
                    macro._gen_context = None
        finally:
            self.nested_resolve -= 1

        if self.nested_resolve > 0:
            return

        try:
            while len(self.to_void) or len(self.to_cancel) or len(self.to_unvoid):
                while len(self.to_void):
                    item, reason = self.to_void.popleft()
                    if isinstance(item, Transformer):
                        manager.cancel_transformer(item, True, reason)
                    elif isinstance(item, Reactor):
                        manager.cancel_reactor(item, True, reason)
                    elif isinstance(item, StructuredCell):
                        scell = item
                        cell = scell._data
                        if cell._destroyed:
                            continue
                        if not scell._data._void:
                            print_debug("***CANCEL***: voided %s" % scell)
                            manager._set_cell_checksum(
                                scell._data, None, status_reason=reason,
                                void=True
                            )
                        accessors_to_cancel = []
                        all_accessors = livegraph.paths_to_downstream.get(cell, {})
                        for accessors in all_accessors.values():
                            accessors_to_cancel += accessors
                        manager.cancel_accessors(accessors_to_cancel, void=True)
                    else:
                        raise TypeError(item)
                while len(self.to_unvoid):
                    item = self.to_unvoid.popleft()
                    if isinstance(item, Transformer):
                        unvoid_transformer(item, livegraph)
                    elif isinstance(item, Reactor):
                        unvoid_reactor(item, livegraph)
                    elif isinstance(item, Macro):
                        unvoid_macro(item, livegraph)
                    elif isinstance(item, StructuredCell):
                        scell = item
                        if scell._exception is not None:
                            print_debug("***CANCEL***: cleared exception for %s" % scell)
                            scell._exception = None
                        if scell._data._void:
                            print_debug("***CANCEL***: unvoided %s" % scell)
                            manager._set_cell_checksum(
                                scell._data, None,
                                void=False
                            )
                        if get_scell_state(scell) == "auth_joining":
                            if scell.auth is not None:
                                scell.auth._void = False
                        if scell.buffer is not None:
                            scell.buffer._void = False
                        for inchannel in scell.inchannels.values():
                            if scell._cyclic and not inchannel._void:
                                continue
                            manager._set_inchannel_checksum(
                                inchannel,
                                None, void=False, from_cancel_system=True
                            )
                        unvoid_scell_all(scell, livegraph)
                    else:
                        raise TypeError(item)
                while len(self.to_cancel):
                    item = self.to_cancel.popleft()
                    if isinstance(item, Transformer):
                        manager.cancel_transformer(item, False)
                    elif isinstance(item, Reactor):
                        manager.cancel_reactor(item, False)
                    elif isinstance(item, StructuredCell):
                        manager.cancel_scell_inpath(item, None, void=False)
                    else:
                        raise TypeError(item)
        finally:
            self.origin_task = None

        #print("/CYCLE2")

    def force_join(self, cyclic_scells):
        old_cyclic_cells = []
        pending_cells = []
        for scell in cyclic_scells:
            if get_scell_state(scell) == "pending":
                pending_cells.append(scell)
            elif scell._cyclic:
                old_cyclic_cells.append(scell)
            else:
                raise ValueError(scell)  # neither cyclic nor pending

        if len(pending_cells):
            msg = "Possible cyclic dependencies detected. Force-joining %d structured cells" % len(pending_cells)
            if len(pending_cells) <= 5:
                msg += ":\n"
                for pending_cell in pending_cells:
                    msg += "   " + str(pending_cell) + "\n"
            else:
                msg += "..."
            print_info(msg)
            to_join = pending_cells
        else:
            # We did a force join cycle already
            # Now let's see if we can un-cycle
            to_join = []
            for scell in old_cyclic_cells:
                checksum = scell._data._checksum
                if scell not in self.cyclic_checksums:
                    print_info("Cyclic, retry", scell)
                    to_join.append(scell)
                elif self.cyclic_checksums[scell] != checksum:
                    print_debug("Cyclic, retry", scell)
                    to_join.append(scell)
                else:
                    print_info("Cyclic => uncyclic", scell)
                    scell._cyclic = False # good, this cell seems to be stable, no change
        manager = self.manager()
        livegraph = manager.livegraph
        for scell in to_join:
            if scell._cyclic and get_scell_state(scell) != "pending":
                self.cyclic_checksums[scell] = scell._data._checksum
            else:
                self.cyclic_checksums.pop(scell, None)
            unvoid_scell_all(scell, livegraph)
            scell._cyclic = True
            scell._joining = True
            StructuredCellJoinTask(manager, scell).launch()
            scell._mode = SCModeEnum.FORCE_JOINING
        return len(to_join)  # there will be change


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
from .tasks.structured_cell import StructuredCellJoinTask, StructuredCellAuthTask
from .unvoid import unvoid_transformer, unvoid_reactor, unvoid_macro, unvoid_scell_all