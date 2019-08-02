from enum import Enum
StatusEnum = Enum("StatusEnum", (
    "OK",
    "PENDING",
    "VOID",
))
StatusReasonEnum = Enum("StatusReasonEnum",(
    "UNCONNECTED",
    "UNDEFINED",
    "INVALID",
    "UPSTREAM",
    "EXECUTING",
))