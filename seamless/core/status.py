class SeamlessInvalidValueError(ValueError):
    pass

class SeamlessUndefinedError(ValueError):
    pass


from enum import Enum

class MyEnum(Enum):
    def __lt__(self, other):
        return self.value < other.value

StatusEnum = MyEnum("StatusEnum", (
    "OK",
    "PENDING",
    "VOID",
))

StatusReasonEnum = MyEnum("StatusReasonEnum",(
    "NONE",
    "UNCONNECTED",
    "UNDEFINED",
    "INVALID", # invalid value
    "ERROR",   # error in execution
    "UPSTREAM", # can be for void or pending; worker or cell
    "EXECUTING",
))

def status_accessor(accessor):
    if accessor._checksum is not None:
        return StatusEnum.OK, StatusReasonEnum.NONE
    if not accessor._void:
        return StatusEnum.PENDING, StatusReasonEnum.UPSTREAM
    return StatusEnum.VOID, accessor._status_reason
    
def status_transformer(transformer):
    if transformer._checksum is not None:
        return StatusEnum.OK, StatusReasonEnum.NONE, None
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
        if reason is None:
            reason = StatusReasonEnum.NONE
        upstreams = livegraph.transformer_to_upstream[transformer]
        if reason == StatusReasonEnum.UNCONNECTED:
            pins = []
            for pinname, accessor in upstreams.items():
                if accessor is None:
                    pins.append(pinname)
        elif reason in (StatusReasonEnum.UNDEFINED, StatusReasonEnum.UPSTREAM):
            pins = {}
            for pinname, accessor in upstreams.items():
                status = status_accessor(accessor)
                if status[0] == StatusEnum.OK:
                    continue
                pins[pinname] = status
    return status, reason, pins
