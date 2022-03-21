from .util import get_path, build_structured_cell

class DeepCellConnector:
    def __init__(self, deep_structure, keyorder):
        self.deep_structure = deep_structure
        self.keyorder = keyorder

def apply_blackwhitelist(origin, keyorder, blackwhitelist):
    assert keyorder is None or isinstance(keyorder, list), keyorder  # TODO: schema instead
    deep_structure = origin
    whitelist = blackwhitelist.get("whitelist")
    if whitelist is not None:
        assert isinstance(whitelist, list)  # TODO: schema instead
        deep_structure = {k:deep_structure[k] for k in whitelist}
        keyorder = [k for k in keyorder if k in whitelist]
    blacklist = blackwhitelist.get("blacklist")
    if blacklist is not None:
        assert isinstance(blacklist, list)  # TODO: schema instead
        deep_structure = {k:deep_structure[k] for k in deep_structure if k not in blacklist}
        keyorder = [k for k in keyorder if k not in blacklist]    
    return deep_structure, keyorder

def translate_deepcell(node, root, namespace, inchannels, outchannels):
    #print("TODO: DeepFolder, probably using this function def")
    # TODO: set schemas for keyorder, blacklist, whitelist
    from .translate import set_structured_cell_from_checksum

    for inchannel in inchannels:
        if inchannel not in ( (), ("blacklist",), ("whitelist",), None ):
            raise AssertionError  # inchannels not allowed, unless black/whitelist or complete assignment

    path = node["path"]

    parent = get_path(root, path[:-1], None, None)
    name = path[-1]
    ctx = context(toplevel=False)
    setattr(parent, name, ctx)

    hash_pattern = {"*": "#"}
    ctx.origin = build_structured_cell(
        parent, name + "_ORIGIN",
        inchannels, [()],
        fingertip_no_remote=node.get("fingertip_no_remote", False),
        fingertip_no_recompute=node.get("fingertip_no_recompute", False),
        hash_pattern=hash_pattern,
        mount=None
    )
    ctx.filtered = build_structured_cell(
        parent, name+"_FILTERED",
        [()], outchannels,
        fingertip_no_remote=node.get("fingertip_no_remote", False),
        fingertip_no_recompute=node.get("fingertip_no_recompute", False),
        hash_pattern=hash_pattern,
        mount=None
    )

    checksum = node.get("checksum")
    if checksum is not None:
        set_structured_cell_from_checksum(ctx.origin, checksum, is_deepcell=True)
    else:
        checksum = {}

    keyorder = core_cell("plain").set_checksum(checksum.get("keyorder"))
    ctx.keyorder = keyorder


    ctx.filtered_keyorder = core_cell("plain")

    namespace[path, "target"] = DeepCellConnector(ctx.origin, ctx.keyorder), node
    for outchannel in outchannels:
        if outchannel == ():
            namespace[path, "source"] = DeepCellConnector(ctx.filtered, ctx.filtered_keyorder), node
        else:
            cpath = path + outchannel
            namespace[cpath, "source"] = ctx.filtered.outchannels[outchannel], node
        
    ctx.blacklist = core_cell("plain")
    ctx.whitelist = core_cell("plain")
    namespace[path + ("blacklist",), "target"] = ctx.blacklist, "target"
    namespace[path + ("whitelist",), "target"] = ctx.whitelist, "target"

    if "blacklist" in checksum:
        ctx.blacklist._set_checksum(checksum["blacklist"], initial=True)
    if "whitelist" in checksum:
        ctx.whitelist._set_checksum(checksum["whitelist"], initial=True)

    ctx.blackwhitelist = build_structured_cell(
        parent, name + "_BLACKWHITELIST",
        [("blacklist",),("whitelist",)],
        [()],
        fingertip_no_remote=False,
        fingertip_no_recompute=False,
        hash_pattern=None,
        mount=None
    )
    empty_dict_cs = 'd0a1b2af1705c1b8495b00145082ef7470384e62ac1c4d9b9cdbbe0476c28f8c' # {}
    set_structured_cell_from_checksum(ctx.blackwhitelist, {"auth": empty_dict_cs})    
    ctx.blacklist.connect(ctx.blackwhitelist.inchannels[("blacklist",)])
    ctx.whitelist.connect(ctx.blackwhitelist.inchannels[("whitelist",)])

    tf_params = {
        "blackwhitelist": {"io": "input", "celltype": "plain"},
        "keyorder": {"io": "input", "celltype": "plain"},
        "origin": {"io": "input", "celltype": "checksum"},
        "result": {"io": "output", "celltype": "plain"},
    }
    ctx.apply_blackwhite = tf = transformer(tf_params)
    ctx.blackwhitelist0 = core_cell("mixed", hash_pattern=hash_pattern)
    ctx.blackwhitelist.outchannels[()].connect(ctx.blackwhitelist0)
    ctx.blackwhitelist0.connect(tf.blackwhitelist)
    ctx.keyorder.connect(tf.keyorder)
    ctx.origin0 = core_cell("mixed", hash_pattern=hash_pattern)
    ctx.origin.outchannels[()].connect(ctx.origin0)
    ctx.origin0.connect(tf.origin)
    tf.code.set(apply_blackwhitelist)
    ctx.filtered_all0 = core_cell("plain")
    tf.result.connect(ctx.filtered_all0)
    ctx.filtered_all = build_structured_cell(
        parent, name + "_FILTERED_ALL",
        [()],
        [(0,),(1,)],
        fingertip_no_remote=False,
        fingertip_no_recompute=False,
        hash_pattern=None,
        mount=None
    )
    ctx.filtered_all0.connect(ctx.filtered_all.inchannels[()])
    
    ctx.filtered_all.outchannels[(1,)].connect(ctx.filtered_keyorder)

    ctx.filtered0 = core_cell("mixed", hash_pattern=hash_pattern)
    ctx.filtered_all.outchannels[(0,)].connect(ctx.filtered0)
    ctx.filtered0.connect(ctx.filtered.inchannels[()])


    return ctx

from seamless.core import cell as core_cell, transformer, context