"""
Translation macro

Translates mid-level into low-level
The mid-level is assumed to be correct; any errors should be caught there

(Any error tracebacks during translation are likely to be cryptic (setattr etc.)
We can't do codegen because not all cells are text!)
"""
from collections import OrderedDict

from seamless.core import cell, transformer, context, macro, StructuredCell
from seamless.core.structured_cell import BufferWrapper

def get_path(root, path, namespace, is_target):
    if namespace is not None:
        hit = namespace.get((path, is_target))
        if hit is not None:
            return hit
        for p, hit_is_target in namespace:
            if hit_is_target != is_target:
                continue
            if path[:len(p)] == p:
                subroot = namespace[p]
                subpath = path[len(p):]
                return get_path(subroot, subpath, None, None)
    c = root
    for p in path:
        c = getattr(c, p)
    return c

def find_channels(path, connection_paths):
    inchannels = []
    outchannels = []
    for source, target in connection_paths:
        if source[:len(path)] == path:
            p = source[len(path):]
            outchannels.append(p)
        if target[:len(path)] == path:
            p = target[len(path):]
            inchannels.append(p)
    return inchannels, outchannels


def build_structured_cell(ctx, name, silk, plain, buffered, inchannels, outchannels):
    name2 = name + "_STRUC"
    c = context(name=name2,context=ctx)
    setattr(ctx, name2, c)
    c.form = cell("json")
    if plain:
        c.data = cell("json")
        storage = None
    else:
        c.storage = cell("text")
        storage = c.storage
        c.data = cell("mixed",
            form_cell = c.form,
            storage_cell = c.storage,
        )
    if silk:
        c.schema = cell("json")
        schema = c.schema
    else:
        schema = None
    if buffered:
        c.buffer_form = cell("json")
        if plain:
            c.buffer_data = cell("json")
            buffer_storage = None
        else:
            c.buffer_storage = cell("text")
            c.buffer_data = cell("mixed",
                form_cell = c.buffer_form,
                storage_cell = c.buffer_storage,
            )
            buffer_storage = c.buffer_storage
        bufferwrapper = BufferWrapper(
            c.buffer_data,
            buffer_storage,
            c.buffer_form
        )
    else:
        bufferwrapper = None

    sc = StructuredCell(
        name,
        c.data,
        storage = storage,
        form = c.form,
        schema = schema,
        buffer = bufferwrapper,
        inchannels = inchannels,
        outchannels = outchannels
    )
    return sc

def translate_py_transformer(node, root, namespace, inchannels, outchannels):
    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    ctx = context(context=parent, name=name)
    setattr(parent, name, ctx)

    result_name = node["RESULT"]
    input_name = node["INPUT"]
    inchannels = [i for i in inchannels if i != "code" and i[0] != "code"]
    for c in inchannels:
        assert (not len(c)) or c[0] != result_name #should have been checked by highlevel

    with_schema = node["with_schema"]
    buffered = node["buffered"]
    interchannels = [tuple(pin) for pin in node["pins"]]
    plain = node["plain"]
    inp = build_structured_cell(ctx, input_name, True, plain, buffered, inchannels, interchannels)
    setattr(ctx, input_name, inp)
    for inchannel in inchannels:
        path = node["path"] + inchannel
        namespace[path, True] = inp.inchannels[inchannel]

    assert result_name not in node["pins"] #should have been checked by highlevel
    all_pins = {}
    for pinname, pin in node["pins"].items():
        p = ["input", pin.get("mode", "copy"), pin.get("submode"), pin.get("celltype")]
        all_pins[pinname] = p
    all_pins[result_name] = "output"
    ctx.tf = transformer(all_pins, with_schema=with_schema)
    ctx.code = cell("pytransformer")
    ctx.code.connect(ctx.tf.code)
    ctx.code.set(node["code"])
    namespace[node["path"] + ("code",), True] = ctx.code

    for pin in list(node["pins"].keys()):
        target = getattr(ctx.tf, pin)
        inp.connect_outchannel( (pin,) ,  target )

    if with_schema:
        plain_result = node["plain_result"]
        outp = build_structured_cell(ctx, result_name, True, plain_result, False, [()], outchannels)
        setattr(ctx, output_name, outp)
        result_pin = getattr(ctx.tf, result_name)
        outp.connect_inchannel(result_pin, ())
    else:
        for c in outchannels:
            assert len(c) == 0 #should have been checked by highlevel
        outp = getattr(ctx.tf, result_name)
        namespace[node["path"] + (result_name,), False] = outp

    handle = ctx.inp.handle
    for path, value in node["values"].items():
        h = handle
        for p in path[:-1]:
            h = getattr(h, p)
        setattr(h, path[-1], value)

    namespace[node["path"], True] = inp
    namespace[node["path"], False] = outp

def translate_cell(node, root, namespace, inchannels, outchannels):
    path = node["path"]
    parent = get_path(root, path[:-1], None, None)
    name = path[-1]
    ct = node["celltype"]
    if ct == "structured":
        buffered = node["buffered"]
        format = node["format"]
        if format in ("mixed", "binary"):
            plain = False
        elif format == "plain":
            plain = True
        else:
            raise ValueError(format)
        silk = node["silk"]
        child = build_structured_cell(parent, name, silk, plain, buffered, inchannels, outchannels)
        schema = node["schema"]
        if schema is not None:
            assert silk
            child.schema.set(schema)
        for inchannel in inchannels:
            cname = child.inchannels[inchannel].name
            if cname == "self":
                cpath = path
            else:
                if isinstance(cname, str):
                    cname = (cname,)
                cpath = path + cname
            namespace[cpath, True] = child.inchannels[inchannel]
        for outchannel in outchannels:
            cpath = path + outchannel
            namespace[cpath, False] = child.outchannels[outchannel]
    else:
        for c in inchannels + outchannels:
            assert not len(c) #should have been checked by highlevel
        assert ct in ("text", "code", "json")
        if ct == "code":
            if node["language"] == "python":
                if node["transformer"]:
                    child = cell("pytransformer")
                else:
                    child = cell("python")
            else:
                child = cell("text")
        else:
            child = cell(ct)
    setattr(parent, name, child)
    value = node["value"]
    if value is not None:
        child.set(value)

def translate_connection(node, namespace, ctx):
    from ..core.structured_cell import Inchannel, Outchannel
    source_path, target_path = node["source"], node["target"]
    source = get_path(ctx, source_path, namespace, False)
    target = get_path(ctx, target_path, namespace, True)
    if isinstance(source, Outchannel):
        name, parent = source.name, source.structured_cell()
        if isinstance(name, str):
            name = (name,)
        parent.connect_outchannel(name, target)
    elif isinstance(target, Inchannel):
        name, parent = target.name, target.structured_cell()
        if isinstance(name, str):
            name = (name,)
        parent.connect_inchannel(source, name)
    else:
        source.connect(target)

def translate(graph, ctx):
    contexts = {con["path"]: con for con in graph if con["type"] == "context"}
    for path in sorted(contexts.keys(), key=lambda k:len(k)):
        parent = get_path(root, path[:-1], None)
        name = path[-1]
        c = context(context=parent, name=name)
        setattr(parent, name, c)
        # No need to add it to namespace, as long as the low-level graph structure is imitated

    connections = [con for con in graph if con["type"] == "connection"]
    connection_paths = [(con["source"], con["target"]) for con in connections]

    namespace = {}
    for node in graph:
        t = node["type"]
        if t == "transformer":
            if node["language"] != "python":
                raise NotImplementedError
            inchannels, outchannels = find_channels(node["path"], connection_paths)
            translate_py_transformer(node, ctx, namespace, inchannels, outchannels)
        elif t == "cell":
            inchannels, outchannels = find_channels(node["path"], connection_paths)
            translate_cell(node, ctx, namespace, inchannels, outchannels)
        elif t in ("context", "connection"):
            pass
        else:
            raise TypeError(t)

    namespace2 = OrderedDict()
    for k in sorted(namespace.keys(), key=lambda k:-len(k)):
        namespace2[k] = namespace[k]

    for node in connections:
        translate_connection(node, namespace2, ctx)
