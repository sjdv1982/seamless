def write_tmp(content):
    tmp = tempfile.mkstemp()[1]
    with open(tmp,"w") as f:
        if content is not None:
            f.write(content)
    return tmp

def merge(upstream, base, modified, labels):
    #NamedTemporaryFile does NOT work properly with diff3!
    tmp1 = write_tmp(upstream)
    tmp2 = write_tmp(base)
    tmp3 = write_tmp(modified)
    try:
        stdout = ""
        cmd = ["diff3", tmp1, tmp2, tmp3, "-m"]
        for n in range(3):
            cmd += ["-L", labels[n]]

        cmd = " ".join(cmd)
        process = subprocess.run(cmd,shell=True,stdout=PIPE,stderr=PIPE)

        if process.returncode == 2:
            print(process.stderr.decode())
            return None, None
        stdout = process.stdout.decode()
    finally:
        os.unlink(tmp1)
        os.unlink(tmp2)
        os.unlink(tmp3)
    return stdout, process.returncode

def analyze_conflict(conflict, labels):
    for token in tokens:
        tokstr = 7 * token + " "
        for label in labels:
            tokstr2 = tokstr + label
            if tokstr2 in conflict:
                return None
    return conflict


def main():
    global mode, upstream, base, modified, labels
    violations = []
    if PINS.upstream_stage.updated:
        violations.append("upstream_stage")
    if PINS.base.updated and mode != "passthrough":
        violations.append("base")

    zero_modify = (not PINS.modified.defined)

    if PINS.modified.updated:
        modified = PINS.modified.value
        if modified.strip() == "":
            zero_modify = True
        else:
            if upstream is None:
                upstream = PINS.upstream.value
            if modified == upstream:
                zero_modify = True

        if zero_modify:
            if mode == "conflict":
                PINS.conflict.set("")
            mode = "passthrough"
    if mode == "passthrough":
        if not zero_modify:
            print()
            mode = "modify"

    if mode == "passthrough": #no modifications at all
        if PINS.conflict.updated and PINS.conflict.value not in ("", "\n", None):
            print("warning: edit pin 'conflict' should not be modified when there is no conflict")
        v = PINS.upstream.value
        PINS.base.set(v)
        PINS.modified.set(v)
        PINS.merged.set(v)
    elif mode == "modify":
        if PINS.conflict.updated and PINS.conflict.value not in ("", "\n", None):
            print("warning: edit pin 'conflict' should not be modified when there is no conflict")
        upstream, base, modified = PINS.upstream.value, PINS.base.value, PINS.modified.value
        if base is None:
            base = upstream
        labels = build_labels(upstream, base, modified)
        merged, has_conflict = merge(upstream, base, modified, labels)
        if merged is None:
            return
        if not has_conflict:
            PINS.merged.set(merged)
            PINS.modified.set(merged)
            PINS.base.set(upstream)
            mode = "modify"
        else:
            PINS.upstream_stage.set(upstream)
            PINS.conflict.set(merged)
            mode = "conflict"
    elif mode == "conflict":
        if PINS.modified.updated or PINS.base.updated or PINS.upstream_stage.updated:
            upstream = PINS.upstream_stage.value
            base = PINS.base.value
            modified = PINS.modified.value
            labels = build_labels(upstream, base, modified)
            merged, has_conflict = merge(upstream, base, modified, labels)
            if merged is None:
                return
            if not has_conflict:
                PINS.merged.set(merged)
                PINS.modified.set(merged)
                PINS.base.set(upstream)
                PINS.conflict.set("")
                mode = "modify"
            else:
                PINS.conflict.set(merged)
        elif PINS.conflict.updated:
            merged = analyze_conflict(PINS.conflict.value, labels)
            if merged is not None:
                PINS.merged.set(merged)
                PINS.modified.set(merged)
                PINS.base.set(upstream)
                PINS.conflict.set("")
                mode = "modify"

    if mode == "conflict":
        if fallback == "no":
            m = None
        elif fallback == "modified":
            m = modified
        elif fallback == "upstream":
            m = upstream
        PINS.merged.set(m)
    for violation in violations:
        print("warning: edit pin '%s' should not be modified" % violation)

if has_diff3:
    if PINS.fallback.updated:
        fallback = PINS.fallback.value
    main()
PINS.mode.set(mode)
