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


def unvoid_cell(cell, livegraph):
    if cell._structured_cell is not None:
        scell = cell._structured_cell
        if scell.buffer is cell:
            return unvoid_scell_inpath(scell, livegraph, ())
        else:
            raise Exception
    if not cell._void:
        return
    cell._void = False
    print_debug("!!!UNVOID!!!: %s" % cell)
    accessors = livegraph.cell_to_downstream.get(cell, None)
    if accessors is None:
        return
    for path in cell._paths:
        path_accessors = livegraph.macropath_to_downstream[path]
        accessors = accessors + path_accessors
    for accessor in accessors:
        unvoid_accessor(accessor, livegraph)

def unvoid_scell_all(scell, livegraph):
    if scell._data._void:
        print_debug("!!!UNVOID!!!: %s" % scell)
    scell._exception = None
    manager = livegraph.manager()
    manager._set_cell_checksum(
        scell._data, None,
        void=False, unvoid=False
    )
    if scell.auth is not None:
        scell.auth._void = False
    if scell.buffer is not None:
        scell.buffer._void = False
    all_accessors = livegraph.paths_to_downstream.get(scell.buffer, {})
    for path in all_accessors:
        for accessor in all_accessors[path]:
            unvoid_accessor(accessor, livegraph)

def unvoid_scell_inpath(scell, livegraph, inpath):
    cell = scell._data
    if cell._destroyed:
        return

    if not cell._void:
        return

    manager = livegraph.manager()
    manager.cancel_scell_inpath(scell, inpath, void=False)


def unvoid_transformer(transformer, livegraph):
    if not transformer._void:
        return
    upstreams = livegraph.transformer_to_upstream[transformer]
    downstreams = livegraph.transformer_to_downstream[transformer]
    if not len(downstreams):
        transformer._status_reason = StatusReasonEnum.UNCONNECTED
        return
    for pinname, accessor in upstreams.items():
        if accessor is None: #unconnected
            transformer._status_reason = StatusReasonEnum.UNCONNECTED
            return
    for pinname, accessor in upstreams.items():
        if accessor._void: #upstream error
            #print("NOT UNVOID", transformer, pinname)
            transformer._status_reason = StatusReasonEnum.UPSTREAM
            return

    print_debug("!!!UNVOID!!!: %s" % transformer)
    transformer._void = False
    accessors = livegraph.transformer_to_downstream.get(transformer, None)
    if accessors is None:
        return
    for accessor in accessors:
        unvoid_accessor(accessor, livegraph)


def unvoid_reactor(reactor, livegraph):
    if not reactor._void:
        return

    rtreactor = livegraph.rtreactors[reactor]
    editpins = rtreactor.editpins
    editpin_to_cell = livegraph.editpin_to_cell[reactor]
    upstreams = livegraph.reactor_to_upstream[reactor]
    outputpins = [pinname for pinname in reactor._pins \
        if reactor._pins[pinname].io == "output" ]

    for pinname, accessor in upstreams.items():
        if accessor is None: #unconnected
            reactor._status_reason = StatusReasonEnum.UNCONNECTED
            return

    for pinname in editpins:
        if editpin_to_cell[pinname] is None: #unconnected
            reactor._status_reason = StatusReasonEnum.UNCONNECTED
            return

    all_downstreams = livegraph.reactor_to_downstream[reactor]
    for outputpin in outputpins:
        if not len(all_downstreams.get(outputpin, [])):
            reactor._status_reason = StatusReasonEnum.UNCONNECTED
            return

    for pinname, accessor in upstreams.items():
        if accessor._void:
            reactor._status_reason = StatusReasonEnum.UPSTREAM
            return

    for pinname in editpins:
        cell = editpin_to_cell[pinname]
        if cell._void: # TODO: allow them to be void? By definition, these cells have authority
            reactor._status_reason = StatusReasonEnum.UPSTREAM
            return

    print_debug("!!!UNVOID!!!: %s" % reactor)
    reactor._void = False

    outputpins = [pinname for pinname in reactor._pins \
        if reactor._pins[pinname].io == "output" ]
    for pinname in outputpins:
        accessors = all_downstreams[pinname]
        for accessor in accessors:
            unvoid_accessor(accessor, livegraph)

def unvoid_macro(macro, livegraph):
    if not macro._void:
        return
    upstreams = livegraph.macro_to_upstream[macro]
    for pinname, accessor in upstreams.items():
        if accessor is None: #unconnected
            macro._status_reason = StatusReasonEnum.UNCONNECTED
            return
    for pinname, accessor in upstreams.items():
        if accessor._void: #upstream error
            macro._status_reason = StatusReasonEnum.UPSTREAM
            return
    print_debug("!!!UNVOID!!!: %s" % macro)
    macro._void = False

def unvoid_accessor(accessor, livegraph):
    if not accessor._void:
        return
    #print("UNVOID ACCESSOR", accessor)
    accessor._void = False
    target = accessor.write_accessor.target()
    if target is None:
        return
    path = accessor.write_accessor.path
    if isinstance(target, MacroPath):
        target = target._cell
    if isinstance(target, Cell) and path is None:
        from_unconnected_cell = False
        source = accessor.source
        if isinstance(source, MacroPath):
            if source._cell is None:
                from_unconnected_cell = True
            else:
                source = source._cell
        if isinstance(source, Cell):
            sc = source._structured_cell
            if sc is not None and accessor.source.path == ():
                if () in sc.inchannels:
                    sreason = sc.inchannels[()]._status_reason
            else:
                sreason = source._status_reason
            if sreason == StatusReasonEnum.UNCONNECTED:
                from_unconnected_cell = True
        if from_unconnected_cell:
            livegraph.manager().cancel_accessor(
                accessor, void=True,
                reason=StatusReasonEnum.UNCONNECTED
            )
        else:
            unvoid_cell(target, livegraph)
    elif isinstance(target, Cell) and path is not None:
        scell = target._structured_cell
        ic = scell.inchannels[path]
        if not ic._void:
            return
        #print("UNVOID INCHANNEL", ic)
        unvoid_scell_inpath(scell, livegraph, path)
    elif isinstance(target, Transformer):
        unvoid_transformer(target, livegraph)
    elif isinstance(target, Reactor):
        unvoid_reactor(target, livegraph)
    elif isinstance(target, Macro):
        unvoid_macro(target, livegraph)
    elif target is None:
        pass
    else:
        raise TypeError(target)


from ..cell import Cell
from ..structured_cell import Inchannel
from ..worker import PinBase, EditPin
from ..transformer import Transformer
from ..reactor import Reactor
from ..macro import Macro, Path as MacroPath
from ..status import StatusReasonEnum
from ..manager.cancel import get_scell_state
from ..manager.tasks.structured_cell import StructuredCellJoinTask