from seamless.core import cell as core_cell, link as core_link, \
 transformer, reactor, context, macro, StructuredCell
import traceback
STRUC_ID = "_STRUC"

def as_tuple(v):
    if isinstance(v, str):
        return (v,)
    else:
        return tuple(v)

def get_path(root, path, namespace, is_target,
  *, until_structured_cell=False,
  return_node=False
 ):    
    if namespace is not None:
        hit = namespace.get((path, is_target))
        if hit is None:
            for p, hit_is_target in namespace:
                if hit_is_target != is_target:
                    continue
                if path[:len(p)] == p:
                    subroot = namespace[p, hit_is_target][0]
                    subpath = path[len(p):]
                    hit = get_path(subroot, subpath, None, None, return_node=True)
        if hit is not None:
            hit, node = hit
            if until_structured_cell:
                if return_node:
                    return hit, node, ()
                else:
                    return hit, ()
            else:
                if return_node:
                    return hit, node
                else:
                    return hit

    c = root
    if until_structured_cell:
        for pnr, p in enumerate(path):
            if isinstance(c, StructuredCell):
                return c, path[pnr:]
            c = getattr(c, p)
        if return_node:
            return c, None, ()
        else:
            return c, ()
    else:
        for p in path:
            c = getattr(c, p)
        if return_node:
            return c, None
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

def build_structured_cell(
  ctx, name,
  inchannels, outchannels,
  *, mount=None, return_context=False,
  hash_pattern=None
):
    if hash_pattern is not None:
        raise NotImplementedError
    #print("build_structured_cell", name)
    name2 = name + STRUC_ID
    c = context(toplevel=False)
    setattr(ctx, name2, c)
    if mount is not None:
        c.mount(**mount)
    c.data = core_cell("mixed")
    c.auth = core_cell("mixed")
    c.schema = core_cell("plain")        
    c.buffer = core_cell("mixed")

    sc = StructuredCell(
        data=c.data,
        auth=c.auth,
        schema=c.schema,
        buffer=c.buffer,
        inchannels=inchannels,
        outchannels=outchannels
    )
    c.example_data = core_cell("mixed")
    c.example_buffer = core_cell("mixed")
    c.example = StructuredCell(
        c.example_data,
        buffer=c.example_buffer,
        schema=c.schema
    )
    if return_context:
        return sc, c
    else:
        return sc
