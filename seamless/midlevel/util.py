from seamless.core import cell as core_cell, \
 transformer, reactor, context, macro, StructuredCell, Outchannel
import traceback
STRUC_ID = "_STRUC"

def as_tuple(v):
    if isinstance(v, str):
        return (v,)
    else:
        return tuple(v)

def get_path_link(root, path, namespace):
    if path[-1] in ("SCHEMA", "RESULTSCHEMA"):
        sc = get_path(root, path[:-1], namespace, True)
        if path[-1] == "SCHEMA":
            if isinstance(sc, Outchannel):
                sc = sc.structured_cell()
            return sc.schema
        else:
            return sc._context().result.schema
    else:
        return get_path(root, path, namespace, False)

def get_path(root, path, namespace, is_target,
  *, until_structured_cell=False,
  return_node=False
 ):
    edit = False
    if namespace is not None:
        for key in namespace:
            assert key[1] in ("source", "target", "edit"), key
        hit = namespace.get((path, "edit"))
        if hit is None:
            cmode0 = "target" if is_target else "source"
            hit = namespace.get((path, cmode0))
        else:
            edit = True
        if hit is None:
            for p, cmode in namespace:
                if cmode != "edit" and cmode != cmode0:
                    continue
                if path[:len(p)] == p:
                    subroot = namespace[p, cmode][0]
                    subpath = path[len(p):]
                    hit = get_path(subroot, subpath, None, None, return_node=True)
        if hit is not None:
            hit, node = hit
            if until_structured_cell:
                if return_node:
                    return hit, node, edit, ()
                else:
                    return hit, ()
            else:
                if return_node:
                    return hit, node, edit
                else:
                    return hit

    c = root
    if until_structured_cell:
        for pnr, p in enumerate(path):
            if isinstance(c, StructuredCell):
                return c, path[pnr:]
            try:
                c = getattr(c, p)
            except AttributeError:
                raise AttributeError(path, p) from None
        if return_node:
            return c, None, edit, ()
        else:
            return c, ()
    else:
        for p in path:
            try:
                c = getattr(c, p)
            except AttributeError:
                raise AttributeError(path, p, c, root) from None
        if return_node:
            return c, None, edit
        else:
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

def cell_setattr(node, ctx, name, c):
    setattr(ctx, name, c)
    if node.get("fingertip_no_recompute"):
        c._fingertip_recompute = False
    if node.get("fingertip_no_remote"):
        c._fingertip_remote = False

def build_structured_cell(
  ctx, name,
  inchannels, outchannels,
  *, fingertip_no_remote, fingertip_no_recompute,
  mount=None, return_context=False,
  hash_pattern=None
):
    #print("build_structured_cell", name)
    name2 = name + STRUC_ID
    c = context(toplevel=False)
    setattr(ctx, name2, c)
    if mount is not None:
        mount.pop("as_directory", None)
        c.mount(**mount)
    c.data = core_cell("mixed")
    c.data._hash_pattern = hash_pattern
    c.auth = core_cell("mixed")
    c.auth._hash_pattern = hash_pattern
    c.schema = core_cell("plain")
    c.buffer = core_cell("mixed")
    c.buffer._hash_pattern = hash_pattern

    sc = StructuredCell(
        data=c.data,
        auth=c.auth,
        schema=c.schema,
        buffer=c.buffer,
        inchannels=inchannels,
        outchannels=outchannels,
        hash_pattern=hash_pattern
    )
    c.example_data = core_cell("mixed")
    c.example_buffer = core_cell("mixed")
    c.example = StructuredCell(
        c.example_data,
        buffer=c.example_buffer,
        schema=c.schema
    )

    for cc in (c.data, c.buffer, c.schema, c.auth, c.example_data, c.example_buffer):
        if fingertip_no_recompute:
            cc._fingertip_recompute = False
        if fingertip_no_remote:
            cc._fingertip_remote = False

    if return_context:
        return sc, c
    else:
        return sc
