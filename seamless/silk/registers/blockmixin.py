from seamless.core.cached_compile import cached_compile

def substitute_error_message(validation_block_lines, eblocks):
    tmpl = "raise SilkValidationError(\"%s\", globals(), locals())"
    # TODO: swallow original exception
    if eblocks is None:
        return validation_block_lines
    ret = []
    for l in validation_block_lines:
        ll = l.lstrip()
        indent = len(l) - len(ll)
        found = False
        for eblock in eblocks:
            code, message = eblock
            if code.strip() == ll.strip():
                m = "    " + tmpl % message
                newlines = ["try:"] + \
                    ["    " + c for c in code.split("\n")] + \
                    [
                      "except Exception as exc:",
                      m
                    ]
                ret.extend([" " * indent + nl for nl in newlines])
                found = True
                break
            if found:
                break
        if not found:
            ret.append(l)
    return ret

def validation_mixin(silkclassname, validation_blocks, error_blocks, properties,
                     namespace):

    eblocks = None
    if error_blocks is not None:
        def strip(ee):
            ee_lines = ee.split("\n")
            change = True
            while change:
                change = False
                if not len(ee_lines[0].strip()):
                    ee_lines = ee_lines[1:]
                    change = True
                if not len(ee_lines[-1].strip()):
                    ee_lines = ee_lines[:-1]
                    change = True
            min_indent = min([len(l) - len(l.lstrip()) \
                              for l in ee_lines if len(l.strip())])
            ee_lines = [m[min_indent:] for m in ee_lines]
            ee = "\n".join(ee_lines)
            return ee

        eblocks = []
        for eblock in error_blocks:
            for e in eblock:
                code = strip(e["code"])
                message = strip(e["message"])
                eblocks.append((code,message))

    myclassname = silkclassname + "_validation_mixin"
    validation_lines = []
    validation_lines2 = []
    for prop in properties:
        validation_lines.append("{0} = self.{0}".format(prop))
    for block in validation_blocks:
        lines = block["text"].split("\n")
        lines = substitute_error_message(lines, eblocks)
        validation_name = "_validation_block_%s" % block["name"]
        validation_lines.append("def %s():" % validation_name)
        for l in lines:
            validation_lines.append("    " + l)
        validation_lines2.append("%s()" % validation_name)
    validation_lines.extend(validation_lines2)
    validation_code = "def _validate(self):\n" + \
        "\n".join(["    " + l for l in validation_lines])
    code_obj = cached_compile(validation_code, myclassname)
    exec(code_obj, namespace)
    ret = type(myclassname, (), {"__slots__":[]})
    namespace[myclassname] = ret
    return ret

def method_mixin(silkclassname, method_blocks, namespace):
    myclassname = silkclassname + "_method_mixin"
    method_lines = []
    method_class_names = []
    for blocknr, block in enumerate(method_blocks):
        lines = block.split("\n")
        method_class_name = "_%s_method_block_%s" % (silkclassname, blocknr+1)
        method_lines.append("class %s:" % method_class_name)
        space = "    "
        for l in lines:
            if len(l.strip()):
                space = "    " + (len(l)-len(l.lstrip())) * " "
                break
        method_lines.append("%s__slots__ = []" % space)
        for l in lines:
            method_lines.append("    " + l)
        method_class_names.append(method_class_name)
    method_code = "\n".join(method_lines)
    code_obj = cached_compile(method_code, myclassname)
    exec(code_obj, namespace)
    method_classes = [namespace[v] for v in method_class_names]
    ret = type(myclassname, tuple(method_classes), {"__slots__":[]})
    namespace[myclassname] = ret
    return ret
