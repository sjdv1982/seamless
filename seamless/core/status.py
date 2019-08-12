class SeamlessInvalidValueError(ValueError):
    pass

class SeamlessUndefinedError(ValueError):
    pass


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

def status_cell(cell):
    if cell._checksum is not None:
        return StatusEnum.OK, None
    if not cell._void:
        return StatusEnum.PENDING, None
    return StatusEnum.VOID, cell._status_reason

def status_accessor(accessor):
    if accessor is None:
        return StatusEnum.VOID, StatusReasonEnum.UNCONNECTED
    if accessor._checksum is not None:
        return StatusEnum.OK, None
    if not accessor._void:
        return StatusEnum.PENDING, None
    return StatusEnum.VOID, accessor._status_reason
    
def status_transformer(transformer):
    if transformer._checksum is not None:
        return StatusEnum.OK, None, None
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
                pins.append(transformer._output_name)
        elif reason == StatusReasonEnum.UPSTREAM:
            pins = {}
            for pinname, accessor in upstreams.items():
                astatus = status_accessor(accessor)
                if astatus[0] == StatusEnum.OK:
                    continue
                pins[pinname] = astatus
    return status, reason, pins

def status_reactor(reactor):
    manager = reactor._get_manager()
    cachemanager = manager.cachemanager
    livegraph = manager.livegraph
    if reactor._pending:
        return StatusEnum.PENDING, None, None
    elif not reactor._void:
        return StatusEnum.OK, None, None
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
    return status, reason, pins

def status_macro(macro):
    if macro._gen_context is not None:
        return StatusEnum.OK, None, None
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
    return status, reason, pins

def format_status(stat):
    status, reason = stat
    if status == StatusEnum.OK:
        return "OK"
    elif status == StatusEnum.PENDING:
        return "pending"
    else:
        if reason is None:
            return "void"
        else:
            return reason.name.lower()

def format_worker_status(stat, as_child=False):
    status, reason, pins = stat
    if status == StatusEnum.OK:
        return "OK"
    elif status == StatusEnum.PENDING:
        if reason == StatusReasonEnum.EXECUTING:
            return "executing"
        else:
            return "pending"
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
        if childstat[0] == StatusEnum.VOID:
            if childstat[1] == StatusReasonEnum.UPSTREAM:
                continue
        if isinstance(child, Worker):            
            res = childname + ": "
            childresult = format_worker_status(childstat, as_child=True)
        elif isinstance(child, Cell):
            res = childname + ": "
            childresult = format_status(childstat)            
        elif isinstance(child, Context):
            res = childname + "\n========\n"            
            childresult = format_context_status(childstat)
        else:
            continue        
        if childresult == "OK":
            continue
        result[res] = childresult
    if not len(result):
        result = "OK"
    return result
