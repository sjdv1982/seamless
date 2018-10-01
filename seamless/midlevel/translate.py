"""
Translation macro

Translates mid-level into low-level
The mid-level is assumed to be correct; any errors should be caught there
"""

from warnings import warn
from collections import OrderedDict
from functools import partial

from seamless.core import cell as core_cell, link as core_link, \
 libcell, libmixedcell, transformer, reactor, context, macro, StructuredCell
from seamless.core.structured_cell import BufferWrapper

from . import copying

STRUC_ID = "_STRUC"

def as_tuple(v):
    if isinstance(v, str):
        return (v,)
    else:
        return tuple(v)

def get_path(root, path, namespace, is_target, until_structured_cell=False):
    if namespace is not None:
        hit = namespace.get((path, is_target))
        if hit is None:
            for p, hit_is_target in namespace:
                if hit_is_target != is_target:
                    continue
                if path[:len(p)] == p:
                    subroot = namespace[p]
                    subpath = path[len(p):]
                    hit = get_path(subroot, subpath, None, None)
        if hit is not None:
            if until_structured_cell:
                return hit, ()
            else:
                return hit

    c = root
    if until_structured_cell:
        for pnr, p in enumerate(path):
            if isinstance(c, StructuredCell):
                return c, path[pnr:]
            c = getattr(c, p)
        return c, ()
    else:
        for p in path:
            c = getattr(c, p)
        return c

def find_channels(path, connection_paths, skip=[]):
    inchannels = []
    outchannels = []
    for source, target in connection_paths:
        if source[:len(path)] == path:
            p = source[len(path):]
            if not len(p) or p[-1] not in skip:
                outchannels.append(p)
        if target[:len(path)] == path:
            p = target[len(path):]
            if not len(p) or p[-1] not in skip:
                inchannels.append(p)
    return inchannels, outchannels

def find_editchannels(path, link_paths, skip=[]):
    editchannels = []
    for first, second in link_paths:
        for point in first, second:
            if point[:len(path)] == path:
                p = point[len(path):]
                if not len(p) or p[-1] not in skip:
                    editchannels.append(p)
    return editchannels

def build_structured_cell(
  ctx, name, silk, plain, buffered,
  inchannels, outchannels, state, lib_path0,
  *, editchannels=[], mount=None,
):
    #print("build_structured_cell", name, lib_path)
    name2 = name + STRUC_ID
    c = context(name=name2,context=ctx)
    setattr(ctx, name2, c)
    if mount is not None:
        c.mount(**mount)
    lib_path = lib_path0 + "." + name2 if lib_path0 is not None else None
    if lib_path:
        path = lib_path + ".form"
        cc = libcell(path)
    else:
        cc = core_cell("json")
    c.form = cc
    if plain:
        if lib_path:
            path = lib_path + ".data"
            cc = libcell(path)
        else:
            cc = core_cell("json")
        c.data = cc
        storage = None
    else:
        if lib_path:
            path = lib_path + ".storage"
            storage = libcell(path)
        else:
            storage = core_cell("text")
        c.storage = storage
        if lib_path:
            path = lib_path + ".data"
            c.data = libmixedcell(path,
                form_cell = c.form,
                storage_cell = c.storage
            )
        else:
            c.data = core_cell("mixed",
                form_cell = c.form,
                storage_cell = c.storage
            )
    if silk:
        if lib_path:
            path = lib_path + ".schema"
            schema = libcell(path)
        else:
            schema = core_cell("json")
        c.schema = schema
    else:
        schema = None
    if buffered:
        if lib_path:
            path = lib_path + ".buffer_form"
            cc = libcell(path)
        else:
            cc = core_cell("json")
        c.buffer_form = cc
        if plain:
            if lib_path:
                path = lib_path + ".buffer_data"
                cc = libcell(path)
            else:
                cc = core_cell("json")
            c.buffer_data = cc
            buffer_storage = None
        else:
            if lib_path:
                path = lib_path + ".buffer_storage"
                buffer_storage = libcell(path)
            else:
                buffer_storage = core_cell("text")
            c.buffer_storage = buffer_storage
            if lib_path:
                path = lib_path + ".buffer_data"
                c.buffer_data = libmixedcell(path,
                    form_cell = c.buffer_form,
                    storage_cell = c.buffer_storage,
                )
            else:
                c.buffer_data = core_cell("mixed",
                    form_cell = c.buffer_form,
                    storage_cell = c.buffer_storage,
                )
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
        outchannels = outchannels,
        state = state,
        editchannels=editchannels
    )
    return sc

def translate_py_transformer(node, root, namespace, inchannels, outchannels, lib_path00, is_lib):
    #TODO: simple translation, without a structured cell
    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    lib_path0 = lib_path00 + "." + name if lib_path00 is not None else None
    ctx = context(context=parent, name=name)
    setattr(parent, name, ctx)

    result_name = node["RESULT"]
    input_name = node["INPUT"]
    if len(inchannels):
        lib_path0 = None #partial authority or no authority; no library update in either case
    for c in inchannels:
        assert (not len(c)) or c[0] != result_name #should have been checked by highlevel

    with_result = node["with_result"]
    buffered = node["buffered"]
    interchannels = [as_tuple(pin) for pin in node["pins"]]
    plain = node["plain"]
    input_state = node.get("stored_state_input", None)
    if input_state is None:
        input_state = node.get("cached_state_input", None)
    inp = build_structured_cell(ctx, input_name, True, plain, buffered, inchannels, interchannels, input_state, lib_path0)
    setattr(ctx, input_name, inp)
    for inchannel in inchannels:
        path = node["path"] + inchannel
        namespace[path, True] = inp.inchannels[inchannel]

    assert result_name not in node["pins"] #should have been checked by highlevel
    all_pins = {}
    for pinname, pin in node["pins"].items():
        p = {"io": "input"}
        p.update(pin)
        all_pins[pinname] = p
    all_pins[result_name] = "output"
    if node["SCHEMA"]:
        assert with_result
        all_pins[node["SCHEMA"]] = {
            "io": "input", "transfer_mode": "json",
            "access_mode": "json", "content_type": "json"
        }
    in_equilibrium = node.get("in_equilibrium", False)
    ctx.tf = transformer(all_pins, in_equilibrium=in_equilibrium)
    if lib_path00 is not None:
        lib_path = lib_path00 + "." + name + ".code"
        ctx.code = libcell(lib_path)
    else:
        ctx.code = core_cell("transformer")
        if "mount" in node:
            ctx.code.mount(**node["mount"])
    ctx.code.connect(ctx.tf.code)
    code = node.get("code")
    if code is None:
        code = node.get("cached_code")
    ctx.code.set(code)
    temp = node.get("TEMP")
    if temp is None:
        temp = {}
    if "code" in temp:
        ctx.code.set(temp["code"])
    inphandle = inp.handle
    for k,v in temp.items():
        if k == "code":
            continue
        setattr(inphandle, k, v)
    namespace[node["path"] + ("code",), True] = ctx.code
    namespace[node["path"] + ("code",), False] = ctx.code

    for pin in list(node["pins"].keys()):
        target = getattr(ctx.tf, pin)
        inp.connect_outchannel( (pin,) ,  target )

    if with_result:
        plain_result = node["plain_result"]
        output_state = node.get("cached_state_output", None)
        result = build_structured_cell(ctx, result_name, True, plain_result, False, [()], outchannels, output_state, lib_path0)
        setattr(ctx, result_name, result)
        result_pin = getattr(ctx.tf, result_name)
        result.connect_inchannel(result_pin, ())
        if node["SCHEMA"]:
            schema_pin = getattr(ctx.tf, node["SCHEMA"])
            result.schema.connect(schema_pin)
    else:
        for c in outchannels:
            assert len(c) == 0 #should have been checked by highlevel
        result = getattr(ctx.tf, result_name)
        namespace[node["path"] + (result_name,), False] = result

    if not is_lib: #clean up cached state and in_equilibrium, unless a library context
        node.pop("cached_state_input", None)
        node.pop("cached_state_result", None)
        node.pop("in_equilibrium", None)

    namespace[node["path"], True] = inp
    namespace[node["path"], False] = result
    node.pop("TEMP", None)

def translate_py_reactor(node, root, namespace, inchannels, outchannels, editchannels, lib_path00, is_lib):
    #TODO: simple-mode translation, without a structured cell
    parent = get_path(root, node["path"][:-1], None, None)
    name = node["path"][-1]
    lib_path0 = lib_path00 + "." + name if lib_path00 is not None else None
    ctx = context(context=parent, name=name)
    setattr(parent, name, ctx)

    io_name = node["IO"]
    if len(inchannels):
        lib_path0 = None #partial authority or no authority; no library update in either case

    buffered = node["buffered"]
    interchannels_in = [as_tuple(p) for p, pin in node["pins"].items() if pin["io"] == "output"]
    interchannels_out = [as_tuple(p) for p, pin in node["pins"].items() if pin["io"] == "input"]
    interchannels_edit = [as_tuple(p) for p, pin in node["pins"].items() if pin["io"] == "edit"]

    all_inchannels = interchannels_in + inchannels  #highlevel must check that there are no duplicates
    all_outchannels = interchannels_out + [p for p in outchannels if p not in interchannels_out]
    all_editchannels = interchannels_edit + [p for p in editchannels if p not in interchannels_edit]

    plain = node["plain"]
    io_state = node.get("stored_state_io", None)
    if io_state is None:
        io_state = node.get("cached_state_io", None)
    io = build_structured_cell(
      ctx, io_name, True, plain, buffered,
      all_inchannels, all_outchannels, io_state, lib_path0,
      editchannels=all_editchannels
    )
    setattr(ctx, io_name, io)
    for inchannel in inchannels:
        path = node["path"] + inchannel
        namespace[path, True] = io.inchannels[inchannel]
    for outchannel in outchannels:
        path = node["path"] + outchannel
        namespace[path, False] = io.outchannels[outchannel]
    for channel in editchannels:
        path = node["path"] + channel
        namespace[path, True] = io.editchannels[channel]
        namespace[path, False] = io.editchannels[channel]

    ctx.rc = reactor(node["pins"])
    for attr in ("code_start", "code_stop", "code_update"):
        if lib_path00 is not None:
            lib_path = lib_path00 + "." + name + "." + attr
            c = libcell(lib_path)
            setattr(ctx, attr, c)
        else:
            c = core_cell("python")
            setattr(ctx, attr, c)
            if "mount" in node and attr in node["mount"]:
                c.mount(**node["mount"][attr])
        c.connect(getattr(ctx.rc, attr))
        code = node.get(attr)
        if code is None:
            code = node.get("cached_" + attr)
        c.set(code)
        namespace[node["path"] + (attr,), True] = c
        namespace[node["path"] + (attr,), False] = c

    for pinname, pin in node["pins"].items():
        target = getattr(ctx.rc, pinname)
        iomode = pin["io"]
        if iomode == "input":
            io.connect_outchannel( (pinname,) ,  target )
        elif iomode == "edit":
            io.connect_editchannel( (pinname,) ,  target )
        elif iomode == "output":
            io.connect_inchannel(target, (pinname,) )

    temp = node.get("TEMP")
    if temp is None:
        temp = {}
    for attr in ("code_start", "code_stop", "code_update"):
        if attr in temp:
            getattr(ctx, attr).set(temp[attr])
    iohandle = io.handle
    for k,v in temp.items():
        if k in ("code_start", "code_stop", "code_update"):
            continue
        setattr(iohandle, k, v)

    if not is_lib: #clean up cached state and in_equilibrium, unless a library context
        node.pop("cached_state_io", None)

    namespace[node["path"], True] = io
    namespace[node["path"], False] = io
    node.pop("TEMP", None)

def translate_cell(node, root, namespace, inchannels, outchannels, editchannels, lib_path0, is_lib, link_target=None):
    path = node["path"]
    parent = get_path(root, path[:-1], None, None)
    name = path[-1]
    ct = node["celltype"]
    if len(inchannels):
        lib_path0 = None #partial authority or no authority; no library update in either case
    if ct == "structured":
        assert not link_target
        buffered = node["buffered"]
        datatype = node["datatype"]
        ### TODO: harmonize datatype with schema type
        if datatype in ("mixed", "array"):
            plain = False
        else: #unknown datatype must be text
            plain = True
        silk = node["silk"]
        state = node.get("stored_state")
        if state is None:
            state = node.get("cached_state")
        mount = node.get("mount")
        child = build_structured_cell(
          parent, name, silk, plain, buffered,
          inchannels, outchannels,
          state, lib_path0, mount=mount, editchannels=editchannels
        )
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
    else: #not structured
        for c in inchannels + outchannels + editchannels:
            assert not len(c) #should have been checked by highlevel
        if link_target:
            child = core_link(link_target)
        elif lib_path0:
            lib_path + lib_path0 + "." + name
            if ct == "mixed": raise NotImplementedError #libmixedcell + cell args
            child = libcell(lib_path)
            #TODO: allow fork to be set
        else:
            if ct == "code":
                if node["language"] == "python":
                    if node["transformer"]:
                        child = core_cell("transformer")
                    else:
                        child = core_cell("python")
                else:
                    child = core_cell("text")
            elif ct in ("text", "json"):
                child = core_cell(ct)
            elif ct in ("mixed", "array", "signal"):
                raise NotImplementedError(ct)
            else:
                raise ValueError(ct) #unknown celltype; should have been caught by high level
    setattr(parent, name, child)
    pathstr = "." + ".".join(path)
    if node.get("TEMP") is not None:
        if link_target is not None:
            warn("Cell %s has a link target, cannot set construction constant" % pathstr)
        else:
            child.set(node["TEMP"])
    if ct != "structured":
        if link_target is not None:
            if "mount" in node:
                warn("Cell %s has a link target, cannot mount" % pathstr)
            stored_value = node.get("stored_value")
            if stored_value is not None:
                warn("Cell %s has a link target, cannot set stored value" % pathstr)
            cached_value = node.get("cached_value")
            if cached_value is not None:
                warn("Cell %s has a link target, cannot set cached value" % pathstr)
        else:
            if "mount" in node:
                child.mount(**node["mount"])
            stored_value = node.get("stored_value")
            if stored_value is not None:
                assert child.authoritative
                child.set(stored_value)
            else:
                cached_value = node.get("cached_value")
                if cached_value is not None:
                    assert not child.authoritative
                    manager = child._get_manager()
                    manager.set_cell(child, cached_value, from_pin=True)


    if not is_lib:
        node.pop("cached_state", None)
    node.pop("TEMP", None)
    return child

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

def translate_link(node, namespace, ctx):
    from ..core.structured_cell import Inchannel, Outchannel, Editchannel, StructuredCell
    first, second = node["first"], node["second"]
    first_simple, second_simple = first["simple"], second["simple"]
    if first["simple"] and second["simple"]:
        return #links between simple cells have been dealt with already, as core.link
    first, subpath_first = get_path(ctx, first["path"], namespace, False, until_structured_cell=True)
    second, subpath_second = get_path(ctx, second["path"], namespace, True, until_structured_cell=True)

    first2, second2 = first, second
    if isinstance(first, StructuredCell):
        assert not first_simple
        first2 = first.editchannels[subpath_first]
    else:
        ###assert first_simple #could come from a CodeProxy!
        pass

    if isinstance(second, StructuredCell):
        assert not second_simple
        second2 = second.editchannels[(subpath_second)]
    else:
        ###assert second_simple #could come from a CodeProxy!
        pass

    #print("LINK!", first_simple, second_simple, first, type(first).__name__, second, type(second).__name__)
    if (not first_simple) and isinstance(first, StructuredCell):
        first.connect_editchannel(subpath_first, second2)
    else:
        first._get_manager().connect_cell(first, second2, duplex=True)

    if (not second_simple) and isinstance(second, StructuredCell):
        second.connect_editchannel(subpath_second, first2)
    else:
        second._get_manager().connect_cell(second, first2, duplex=True)

def translate(graph, ctx, from_lib_paths, is_lib):
    ###import traceback; stack = traceback.extract_stack(); print("TRANSLATE:"); print("".join(traceback.format_list(stack[:3])))
    contexts = {con["path"]: con for con in graph if con["type"] == "context"}
    for path in sorted(contexts.keys(), key=lambda k:len(k)):
        parent = get_path(ctx, path[:-1], None, is_target=False)
        name = path[-1]
        c = context(context=parent, name=name)
        setattr(parent, name, c)
        # No need to add it to namespace, as long as the low-level graph structure is imitated

    connections = [con for con in graph if con["type"] == "connection"]
    connection_paths = [(con["source"], con["target"]) for con in connections]
    links = [con for con in graph if con["type"] == "link"]
    link_paths = [(node["first"]["path"], node["second"]["path"]) for node in links]

    lowlevel_links = {}
    #multiple links (A,B), (A,C) are allowed; A becomes the real one
    #multiple links (B,A), (C,A) are not allowed
    #multiple links (A,B), (A,C), (D,A), (E,D) leads to A,B,C,D => E, E as the real one
    simple_links = []
    for node in links:
        first, second = node["first"], node["second"]
        if not first["simple"]:
            continue
        if not second["simple"]:
            continue
        first, second = first["path"], second["path"]
        simple_links.append((first, second))
        assert second not in lowlevel_links
        lowlevel_links[second] = first

    change = True
    while change:
        change = False
        simple_links0 = simple_links
        simple_links = []
        for first, second in simple_links0:
            while first in lowlevel_links:
                first = lowlevel_links[first]
                change = True
            lowlevel_links[second] = first
            simple_links.append((first, second))

    link_target_paths = set(lowlevel_links.values())
    link_targets = {} #maps "first" paths of a link (aka link target paths, aka "real cells") to their translated cells

    namespace = {}
    for node in graph:
        t = node["type"]
        if t in ("context", "connection", "link"):
            continue
        path = node["path"]
        lib_path = get_lib_path(path[:-1], from_lib_paths)
        if t == "cell" and path in link_target_paths:
            assert node["celltype"] != "structured" #low-level links are between simple cells!
            inchannels, outchannels = find_channels(path, connection_paths)
            editchannels = find_editchannels(path, link_paths)
            translated_cell = translate_cell(node, ctx, namespace, inchannels, outchannels, editchannels, lib_path, is_lib)
            link_targets[path] = translated_cell

    #print("LOW-LEVEL LINKS", lowlevel_links)
    #print("LOW-LEVEL LINK TARGETS", link_targets)

    for node in graph:
        t = node["type"]
        if t in ("context", "connection", "link"):
            continue
        path = node["path"]
        lib_path = get_lib_path(path[:-1], from_lib_paths)
        if t == "transformer":
            if node["language"] != "python":
                raise NotImplementedError
            skip_channels = ("code",)
            inchannels, outchannels = find_channels(node["path"], connection_paths, skip_channels)
            translate_py_transformer(node, ctx, namespace, inchannels, outchannels, lib_path, is_lib)
        elif t == "reactor":
            if node["language"] != "python":
                raise NotImplementedError
            skip_channels = ("code_start", "code_update", "code_stop")
            inchannels, outchannels = find_channels(node["path"], connection_paths, skip_channels)
            editchannels = find_editchannels(node["path"], link_paths, skip_channels)
            translate_py_reactor(node, ctx, namespace, inchannels, outchannels, editchannels, lib_path, is_lib)
        elif t == "cell":
            if path in link_target_paths:
                continue #done already before
            inchannels, outchannels = find_channels(path, connection_paths)
            editchannels = find_editchannels(path, link_paths)
            link_target = None
            if path in lowlevel_links:
                link_target = link_targets[lowlevel_links[path]]
            translate_cell(node, ctx, namespace, inchannels, outchannels, editchannels, lib_path, is_lib, link_target=link_target)
        else:
            raise TypeError(t)

    namespace2 = OrderedDict()
    for k in sorted(namespace.keys(), key=lambda k:-len(k)):
        namespace2[k] = namespace[k]

    for node in links:
        translate_link(node, namespace2, ctx)

    for node in connections:
        translate_connection(node, namespace2, ctx)

from .library import get_lib_path
