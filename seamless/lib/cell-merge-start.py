if PINS.conflict.defined:
    mode = "conflict"
elif not PINS.modified.defined or PINS.modified.value == PINS.base.value:
    mode = "passthrough"
else:
    mode = "modify"
