from seamless.core import cell as core_cell, link as core_link, \
 libcell, libmixedcell, transformer, reactor, context, macro, StructuredCell
from seamless.core.structured_cell import BufferWrapper
import traceback
STRUC_ID = "_STRUC"

def try_set(cell, value):
    #TODO: proper logging
    try:
        cell.set(value)
    except:
        traceback.print_exc()

def try_set2(cell, manager, value, *args, **kwargs):
    #TODO: proper logging
    try:
        manager.set_cell(cell, value, *args, **kwargs)
    except:
        traceback.print_exc()


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
  *, editchannels=[], mount=None, return_context=False
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
    if return_context:
        return sc, c
    else:
        return sc
