print("mode", mode)
violations = []
if PINS.upstream_stage.updated:
    violations.append("upstream_stage")
if PINS.base.updated and mode != "passthrough":
    violations.append("base")
if mode == "passthrough": #no modifications at all
    if PINS.conflict.updated:
        print("warning: edit pin 'conflict' should not be modified when there is no conflict")
    v = PINS.upstream.value
    print("V", v)
    PINS.base.set(v)
    PINS.modified.set(v)
    PINS.merged.set(v)
elif mode == "modify":
    if PINS.conflict.updated:
        print("warning: edit pin 'conflict' should not be modified when there is no conflict")

for violation in violations:
    print("warning: edit pin '%s' should not be modified" % violation)
