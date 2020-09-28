"""
Code to deal with structured cells that, from a signal propagation point-of-view, are *complex*.

For complex scells, we can't predict immediately what happens when a single inchannel is canceled or unvoided:
 at the end of the cancel/unvoid cycle, we must consider the structured cell as a whole.

Scells are complex if they have EITHER:
  - a schema and at least one outchannel
  OR:
  - outchannels that are determined partially-but-not-completely by an inchannel.
In the second case, the scell is always complex. In the first case, it will become complex after going
 through a pending+ state (because of _modified_schema) and a join.

"""
def scell_is_complex(scell):
    if scell.schema is not None and scell.schema._checksum is not None:
        if len(scell.outchannels):
            return True
        else:
            return False
    else:
        for out_path in scell.outchannels:
            for in_path in scell.inchannels:
                if len(in_path) <= len(out_path):
                    continue
                if in_path[:len(out_path)] == out_path:
                    return True
        return False


def get_scell_state(scell, verbose=False):
    """Returns the state for a structured cell.

    Result:

    void :     The structured cell and all outchannels must be voided
    pending:   Outchannels should be voided/unvoided based on overlap with the inchannel channel.
               For non-complex scells, this can be done whenever an inchannel changes
               For complex scells, voiding/unvoiding must happen holistically
    pending+ : auth or schema have been modified. Everything must be unvoided. A join should already be underway.
    devalued-: Only for complex scells.
               The scell is currently non-void.
               Some inchannels have been devalued (voided) since the last join
               A join is needed, and the schema might then void the scell.
    devalued+: Only for complex scells.
               The scell is currently void, because of a schema exception.
               Some inchannels have been devalued (voided) since the last join
               A join is needed, and the schema might then unvoid the scell.
               In the meantime, unvoid everything.
    equilibrium: nothing will change.
               The structured cell is not void. Some inchannels and outchannels are void, others not.
    join:      There are valid inchannels and/or an auth value.
               There are no pending inchannels or auth modifications, but no value has yet been set.
               Verify that a join is underway, or else launch one.
    """
    is_complex = scell_is_complex(scell)
    auth_modified = scell._modified_auth or scell._modified_schema
    auth_invalid = scell._auth_invalid
    pending_inchannels = {k for k,ic in scell.inchannels.items() if (ic._checksum is None and not ic._void)}
    valid_inchannels = {k for k,ic in scell.inchannels.items() if not ic._void}
    devalued_inchannels = {k for k,ic in scell.inchannels.items() if (ic._void and ic._last_state[1] is not None)}
    has_auth = scell.auth is not None and scell.auth._checksum is not None
    has_exc = scell._exception is not None and not auth_invalid

    if auth_modified:
        result = "pending+"
    elif auth_invalid:
        result = "void"
    elif len(pending_inchannels):
        result = "pending"
    elif not has_auth and not len(valid_inchannels):
        result = "void"
    else:
        if len(scell.inchannels):
            if has_exc:
                if not is_complex:  # exc must be from inchannel parsing or cache misses
                    result = "void"
                else:
                    if len(devalued_inchannels):  # exc could be from validation => voiding an inchannel could actually lead to an unvoid
                        result = "devalued+"
                    else:
                        result = "void"
            else:
                if scell._data._checksum is None:
                    result = "join"
                else:
                    if not is_complex:
                        result = "equilibrium"
                    else:
                        if len(devalued_inchannels):
                            result = "devalued-"
                        else:
                            result = "equilibrium"
        else: # implies has_auth, and also implies not complex
            if scell._data._checksum is None:
                result = "join"
            else:
                result = "equilibrium"

    if verbose:
        print("STATE", scell, result, is_complex, auth_modified, auth_invalid, pending_inchannels, valid_inchannels, devalued_inchannels, has_auth, has_exc)

    return result

def _update_outchannel_accessor(scell, outpath, accessor, to_void, to_unvoid, err, taskmanager):
    has_auth = scell.auth is not None and scell.auth._checksum is not None
    if accessor._checksum is None:
        for inpath, ic in scell.inchannels.items():
            if ic._checksum is None and not ic._void:
                if overlap_path(inpath, outpath):
                    accessor._soften = True
                    if accessor._void:
                        to_unvoid.append(accessor)
                    return
        accessor._soften = False
        if not len(taskmanager.accessor_to_task.get(accessor, [])) and scell._exception is None:
            for inpath, ic in scell.inchannels.items():
                if ic._checksum is not None and not ic._void and ic._last_state[1] is not None:
                    if outpath[:len(inpath)] == inpath:
                        print("WARNING: %s outchannel \"%s\" should have a value from \"%s\", but hasn't" % (scell, outpath, inpath))
                        err.append((outpath, accessor))
                        return
            if not accessor._void:
                to_void.append(accessor)
    else:
        for inpath, ic in scell.inchannels.items():
            if ic._void:
                if outpath[:len(inpath)] == inpath:
                    print("WARNING: %s outchannel \"%s\" shouldn't have a value (1)" % (scell, outpath))
                    err.append((outpath, accessor))
                    return
        for inpath, ic in scell.inchannels.items():
            if ic._checksum is None and not ic._void:
                if overlap_path(inpath, outpath):
                    return
        else:
            if not has_auth:
                for inpath, ic in scell.inchannels.items():
                    if ic._checksum is not None:
                        if overlap_path(inpath, outpath):
                            return
                print("WARNING: %s outchannel \"%s\" shouldn't have a value (2)" % (scell, outpath))
                err.append((outpath, accessor))




def update_outchannels(scell, manager, origin_task):
    """
    Only call this function outside the resolve cycle
    For an outchannel accessor with checksum None:
       if covered at least partially by a pending inchannel, it is pending and softened
       else:
           - it is not softened
           - if no accessor update in progress:
                - it is voided
                - it must not covered fully by a valued inchannel, or something fishy is going on

    For an outchannel accessor with a value:
        if covered fully by a void inchannel, something fishy is going on  (it should be in "devalued-" status)
        if covered partially by a pending inchannel:
            nothing to do
        else:
            - it must be covered at least partially by a valued inchannel
            - or: auth must not be empty
            - else: something fishy is going on

            nothing to do
    """
    taskmanager = manager.taskmanager
    joins = taskmanager.structured_cell_to_task.get(scell, [])
    if len(joins) > 1 or (len(joins) == 1 and joins[0] is not origin_task):
        return
    if manager is None or manager._destroyed:
        return
    livegraph = manager.livegraph
    all_accessors = livegraph.paths_to_downstream.get(scell._data, {})
    to_unvoid = []
    to_void = []
    err = []
    for outpath in all_accessors:
        for accessor in all_accessors[outpath]:
            _update_outchannel_accessor(scell, outpath, accessor, to_void, to_unvoid, err, taskmanager)
    for accessor in to_unvoid:
        unvoid_accessor(accessor, livegraph)
        manager.cancel_accessor(accessor, False, origin_task=origin_task)
    for accessor in to_void:
        manager.cancel_accessor(accessor, True, origin_task=origin_task)
    if len(err):
        manager.structured_cell_join(scell, False)
    else:
        new_state = get_scell_state(scell)
        if new_state == "equilibrium":
            scell._equilibrated = True

def resolve_complex_scell(cycle, scell, post_join):
    if scell._destroyed:
        return
    new_state = get_scell_state(scell)
    if post_join and (scell._exception is not None or scell._auth_invalid):
        new_state = "void"

    taskmanager = cycle.taskmanager
    manager = cycle.manager()
    if manager is None or manager._destroyed:
        return
    has_joins = len(taskmanager.structured_cell_to_task.get(scell, []))
    #print("RESOLVE COMPLEX", scell, new_state, scell._equilibrated)
    if new_state == "pending+" or new_state == "join":
        if new_state == "pending+":
            scell._equilibrated = False
        if not has_joins and not post_join:
            if new_state == "pending+":
                print("WARNING: %s is in state '%s' but no joins were launched" % (scell, new_state))
                get_scell_state(scell, verbose=True)
                import traceback
                traceback.print_stack()
                manager.structured_cell_join(scell, False)
            if scell not in cycle.to_join:
                cycle.to_join.append(scell)
        if scell not in cycle.to_unvoid:
            cycle.to_unvoid.append(scell)
        return
    if new_state == "pending":
        if post_join:
            cycle.to_soft_cancel.append(scell)
            return
        scell._equilibrated = False
        if scell._data._void:
            if scell not in cycle.to_unvoid:
                cycle.to_unvoid.append(scell)
        if not has_joins:
            #update_outchannels(scell, cycle.manager(), cycle.origin_task)
            args = (scell, cycle.manager(), cycle.origin_task)
            cycle.to_update.append(args)
        return

    if new_state == "devalued+":
        scell._equilibrated = False
        if scell not in cycle.to_join:
            cycle.to_join.append(scell)
        if scell not in cycle.to_unvoid:
            cycle.to_unvoid.append(scell)
        return

    if new_state == "void":
        if scell._data._void and not post_join:
            return
        if scell._auth_invalid:
            reason = StatusReasonEnum.INVALID
        elif scell._exception is not None and scell.buffer._checksum is not None:
            reason = StatusReasonEnum.INVALID
        else:
            reason = scell._data._status_reason
            if reason is None:
                reason = StatusReasonEnum.UPSTREAM
        cycle.to_void[:] = [item for item in cycle.to_void if item[0] is not scell]
        cycle.to_void.append((scell, reason))
        return

    if new_state == "devalued-":
        scell._equilibrated = False
        if scell not in cycle.to_join:
            cycle.to_join.append(scell)
        return

    if new_state == "equilibrium":
        if (not has_joins) or post_join:
            if not scell._equilibrated:
                #update_outchannels(scell, cycle.manager(), cycle.origin_task)
                args = (scell, cycle.manager(), cycle.origin_task)
                cycle.to_update.append(args)
        return

    raise ValueError(new_state)

def unvoid_complex_scell(cycle, scell):
    if scell._destroyed:
        return

    scell._equilibrated = False
    scell._exception = None
    scell._data._void = False

    if scell.auth is not None:
        scell.auth._void = False
    if scell.buffer is not None:
        scell.buffer._void = False

    manager = cycle.manager()
    if manager is None or manager._destroyed:
        return
    livegraph = manager.livegraph
    all_accessors = livegraph.paths_to_downstream.get(scell._data, {})
    for accessors in all_accessors.values():
        for accessor in accessors:
            unvoid_accessor(accessor, livegraph)



from ..utils import overlap_path
from .unvoid import unvoid_accessor
from ..status import StatusReasonEnum