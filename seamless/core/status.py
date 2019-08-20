class SeamlessInvalidValueError(ValueError):
    pass

class SeamlessUndefinedError(ValueError):
    pass

import json
from enum import Enum

class MyEnum(Enum):
    def __lt__(self, other):
        if other is None:
            return False
        return self.value < other.value
    def __eq__(self, other):
        if other is None:
            return False
        return self.value == other.value

StatusEnum = MyEnum("StatusEnum", (
    "OK",
    "PENDING",
    "SUB",
    "VOID",
))

StatusReasonEnum = MyEnum("StatusReasonEnum",(
    "UNCONNECTED", # only for workers
    "UNDEFINED", # only for cells
    "INVALID", # invalid value; worker or cell
    "ERROR",   # error in execution; only for workers
    "UPSTREAM", # worker or cell
    "EXECUTING" # only for workers, only for pending
))

class WorkerStatus:
    def __init__(self,
        status,
        reason=None,
        pins=None,
        preliminary=False,
        progress=0.0
    ):
        self.status = status
        self.reason = reason
        self.pins = pins
        self.preliminary = preliminary
        self.progress = progress
    
    def __getitem__(self, index):
        if index == 0:
            return self.status
        if index == 1:
            return self.reason
        raise IndexError(index)

    def __str__(self):
        return str(self.__dict__)

    def __repr__(self):
        return repr(self.__dict__)

def status_cell(cell):
    if cell._checksum is not None:
        return StatusEnum.OK, None, cell._prelim
    if not cell._void:
        return StatusEnum.PENDING, None, None
    return StatusEnum.VOID, cell._status_reason, None

def status_accessor(accessor):
    if accessor is None:
        return StatusEnum.VOID, StatusReasonEnum.UNCONNECTED, None
    if accessor._checksum is not None:
        return StatusEnum.OK, None, accessor._prelim
    if not accessor._void:
        return StatusEnum.PENDING, None, None
    return StatusEnum.VOID, accessor._status_reason, None
    
def status_transformer(transformer):
    prelim = transformer.preliminary
    checksum = transformer._checksum
    if checksum is not None and not prelim:
        return WorkerStatus(StatusEnum.OK)
    manager = transformer._get_manager()
    tcache = manager.cachemanager.transformation_cache
    livegraph = manager.livegraph
    pins = None
    if not transformer._void:
        status = StatusEnum.PENDING
        reason = StatusReasonEnum.UPSTREAM
        tf_checksum = tcache.transformer_to_transformations.get(transformer)
        if tf_checksum is not None:
            if tf_checksum in tcache.transformation_jobs:
                reason = StatusReasonEnum.EXECUTING
        if reason == StatusReasonEnum.UPSTREAM:
            if checksum is not None:
                assert prelim
                return WorkerStatus(StatusEnum.OK, preliminary=True)
    else:
        status = StatusEnum.VOID
        reason = transformer._status_reason
        upstreams = livegraph.transformer_to_upstream[transformer]
        downstreams = livegraph.transformer_to_downstream[transformer] 
        if reason == StatusReasonEnum.UNCONNECTED:
            pins = []
            for pinname, accessor in upstreams.items():
                if accessor is None:
                    pins.append(pinname)
            if not len(downstreams):
                outp = transformer._output_name
                assert outp is not None
                pins.append(outp)
        elif reason == StatusReasonEnum.UPSTREAM:
            pins = {}
            for pinname, accessor in upstreams.items():
                astatus = status_accessor(accessor)
                if astatus[0] == StatusEnum.OK:
                    continue
                pins[pinname] = astatus
    return WorkerStatus(
        status, reason, pins,
        preliminary = transformer.preliminary,
        progress = transformer._progress
    )

def status_reactor(reactor):
    manager = reactor._get_manager()
    cachemanager = manager.cachemanager
    livegraph = manager.livegraph
    if reactor._pending:
        return WorkerStatus(StatusEnum.PENDING)
    elif not reactor._void:
        return WorkerStatus(StatusEnum.OK)
    rtreactor = livegraph.rtreactors[reactor]

    status = StatusEnum.VOID
    reason = reactor._status_reason
    upstreams = livegraph.reactor_to_upstream[reactor]
    pins = None
    if reason == StatusReasonEnum.UNCONNECTED:
        pins = []
        for pinname, accessor in upstreams.items():
            if accessor is None:
                pins.append(pinname)
    elif reason == StatusReasonEnum.UPSTREAM:
        pins = {}
        for pinname, accessor in upstreams.items():
            astatus = status_accessor(accessor)
            if astatus[0] == StatusEnum.OK:
                continue
            pins[pinname] = astatus
        for pinname in rtreactor.editpins:
            cell = livegraph.editpin_to_cell[reactor][pinname]
            astatus = status_accessor(cell)
            if astatus[0] == StatusEnum.OK:
                continue
            pins[pinname] = astatus

    return WorkerStatus(
        status, reason, pins
    )

def status_macro(macro):
    if macro._gen_context is not None:
        assert not macro._void
        gen_status = macro._gen_context._get_status()
        if format_context_status(gen_status) != "OK":
            return WorkerStatus(
                StatusEnum.SUB, None, gen_status
            )
        return WorkerStatus(StatusEnum.OK)
    manager = macro._get_manager()
    livegraph = manager.livegraph
    pins = None
    if not macro._void:
        status = StatusEnum.PENDING
        reason = StatusReasonEnum.UPSTREAM
    else:
        status = StatusEnum.VOID
        reason = macro._status_reason
        upstreams = livegraph.macro_to_upstream[macro]
        if reason == StatusReasonEnum.UNCONNECTED:
            pins = []
            for pinname, accessor in upstreams.items():
                if accessor is None:
                    pins.append(pinname)
        elif reason == StatusReasonEnum.UPSTREAM:
            pins = {}
            for pinname, accessor in upstreams.items():
                astatus = status_accessor(accessor)
                if astatus[0] == StatusEnum.OK:
                    continue
                pins[pinname] = astatus
    return WorkerStatus(status, reason, pins)

def format_status(stat):
    status, reason, prelim = stat
    if status == StatusEnum.OK:
        if prelim:
            return "preliminary"
        else:
            return "OK"
    elif status == StatusEnum.PENDING:
        return "pending"
    else:
        if reason is None:
            return "void"
        else:
            return reason.name.lower()

def format_worker_status(stat, as_child=False):
    status, reason, pins = (
        stat.status, stat.reason, stat.pins
    )
    if status == StatusEnum.OK:
        if stat.preliminary:
            return "preliminary"
        return "OK"
    elif status == StatusEnum.PENDING:
        if reason == StatusReasonEnum.EXECUTING:
            progress = stat.progress
            if progress > 0:
                return "executing, %.1f %%" % progress
            else:
                return "executing"
        else:
            return "pending"
    elif status == StatusEnum.SUB:
        sub = pins
        ctx_status = format_context_status(sub)
        ctx_statustxt = json.dumps(ctx_status, indent=2, sort_keys=True)
        return ("macro ctx =>", ctx_status)
    else:
        if reason == StatusReasonEnum.UNCONNECTED:
            result = "unconnected => "
            result += ", ".join(pins)
        elif reason == StatusReasonEnum.UPSTREAM:
            result = reason.name.lower() + " => "
            pinresult = []
            for pinname, pstatus in pins.items():
                if as_child:                                
                    pinresult.append(pinname)
                else:
                    pinresult.append(pinname + " " + format_status(pstatus))
            result += ", ".join(pinresult)
        else:
            result = reason.name.lower()
        return result

def format_context_status(stat):
    from .worker import Worker
    from .cell import Cell
    from .context import Context
    result = {}
    for childname, value in stat.items():
        child, childstat = value
        if not isinstance(child, Context):
            if childstat[0] == StatusEnum.VOID:
                if childstat[1] == StatusReasonEnum.UPSTREAM:
                    continue
            if childstat[0] == StatusEnum.PENDING:
                if isinstance(child, Worker):
                    if childstat.reason != StatusReasonEnum.EXECUTING:
                        continue  
                else:
                    continue
        if isinstance(child, Worker):
            childresult = format_worker_status(childstat, as_child=True)
        elif isinstance(child, Cell):
            childresult = format_status(childstat)            
        elif isinstance(child, Context):
            childresult = format_context_status(childstat)
        else:
            continue        
        if childresult == "OK":
            continue
        result[childname] = childresult
    if not len(result):
        result = "OK"
    return result
