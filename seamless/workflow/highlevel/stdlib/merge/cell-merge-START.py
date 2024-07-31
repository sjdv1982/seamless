import tempfile, os
from seamless import subprocess
from seamless.subprocess import PIPE
tokens = "<|>"
labels0 = "UPSTREAM", "BASE", "MODIFIED"

no_conflict = "No conflict"

class SeparatorInTextError(Exception):
    pass

def build_labels(upstream, base, modified):
    n = ""
    while 1:
        try:
            for token in tokens:
                tokstr = 7 * token + " "
                for label in labels0:
                    tokstr2 = tokstr + label + str(n)
                    for text in upstream, base, modified:
                        if text is None:
                            continue
                        if text.find(tokstr2) > -1:
                            raise SeparatorInTextError
        except SeparatorInTextError:
            if n == "":
                n = 0
            n += 1
            continue
        break
    return tuple([l+str(n) for l in labels0])

upstream, base, modified = None, None, None
if PINS.conflict.defined and PINS.conflict.value.strip("\n ") not in ("",  no_conflict):
    state = "conflict"
    upstream = PINS.upstream_stage.value
    base = PINS.base.value
    modified = PINS.modified.value
    labels = build_labels(upstream, base, modified)
elif not PINS.modified.defined or PINS.modified.value == PINS.base.value:
    state = "passthrough"
else:
    state = "modify"

if state != "conflict":
    PINS.conflict.set(no_conflict)
fallback_mode = PINS.fallback_mode.value