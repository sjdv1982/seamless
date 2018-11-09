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

from . import copying
from .util import as_tuple, get_path, find_channels, find_editchannels, build_structured_cell, try_set, try_set2



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
            c._sovereign = True
            setattr(ctx, attr, c)
            if "mount" in node and attr in node["mount"]:
                c.mount(**node["mount"][attr])
        c.connect(getattr(ctx.rc, attr))
        code = node.get(attr)
        if code is None:
            code = node.get("cached_" + attr)
        try_set(c, code)
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
            try_set(getattr(ctx, attr), temp[attr])
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
            child._sovereign = True
    setattr(parent, name, child)
    pathstr = "." + ".".join(path)
    if node.get("TEMP") is not None:
        if link_target is not None:
            warn("Cell %s has a link target, cannot set construction constant" % pathstr)
        else:
            try_set(child, node["TEMP"])
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
            if "file_extension" in node:
                child.set_file_extension(node["file_extension"])
            if "mount" in node:
                child.mount(**node["mount"])
            stored_value = node.get("stored_value")
            if stored_value is not None:
                assert child.authoritative
                try_set(child, stored_value)
            else:
                cached_value = node.get("cached_value")
                if cached_value is not None:
                    ###assert not child.authoritative
                    if not child.authoritative:
                        manager = child._get_manager()
                        try_set2(child, manager, cached_value, from_pin=True)


    if not is_lib:
        node.pop("cached_state", None)
    node.pop("TEMP", None)
    return child

def translate_connection(node, namespace, ctx):
    from ..core.structured_cell import Inchannel, Outchannel
    source_path, target_path = node["source"], node["target"]

    source = get_path(ctx, source_path, namespace, False)
    if isinstance(source, StructuredCell):
        source = source.outchannels[()]
    target = get_path(ctx, target_path, namespace, True)
    if isinstance(target, StructuredCell):
        target = target.inchannels[()]

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
            skip_channels = ("code",)
            inchannels, outchannels = find_channels(node["path"], connection_paths, skip_channels)
            if node["compiled"]:
                from .translate_compiled_transformer import translate_compiled_transformer
                translate_compiled_transformer(node, ctx, namespace, inchannels, outchannels, lib_path, is_lib)
            elif node["language"] == "python":
                translate_py_transformer(node, ctx, namespace, inchannels, outchannels, lib_path, is_lib)
            else:
                raise NotImplementedError
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
from .translate_py_transformer import translate_py_transformer
