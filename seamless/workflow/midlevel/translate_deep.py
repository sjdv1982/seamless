from seamless.checksum.buffer_cache import empty_list_checksum
from .util import get_path, build_structured_cell
from ..core import cell as core_cell, transformer, reactor, context

option_reactor_code = """
def update_from_upstream():
    global selected_option
    if len(upstream) == 2 and options is not None:
        selected_option = None
        try:
            for k,v in options.items():
                if v == upstream:
                    selected_option = k
                    break
        except Exception:
            pass
        PINS.selected_option.set(selected_option)

def update_from_selected_option():
    if options is not None and selected_option is not None:
        try:
            value = options[selected_option]
        except Exception:
            pass
        else:
            PINS.origin_integrated0.set(value["checksum"])
            PINS.keyorder_integrated0.set(value["keyorder"])

if PINS.options.updated:
    options = PINS.options.value
    if last_value == "upstream":
        update_from_upstream()
    elif last_value == "selected_option":
        update_from_selected_option()
if PINS.keyorder.updated:
    keyorder = PINS.keyorder.value
    PINS.keyorder_integrated0.set(keyorder)
    upstream["keyorder"] = keyorder
    last_value = "upstream"
    if not PINS.origin.updated:
        update_from_upstream()
if PINS.origin.updated:
    origin = PINS.origin.value
    PINS.origin_integrated0.set(origin)
    upstream["checksum"] = origin
    last_value = "upstream"
    update_from_upstream()
elif PINS.selected_option.updated:
    selected_option = PINS.selected_option.value
    last_value = "selected_option"
    update_from_selected_option()
"""


class DeepCellConnector:
    def __init__(self, deep_structure, keyorder):
        self.deep_structure = deep_structure
        self.keyorder = keyorder


def apply_blackwhitelist(origin, keyorder, blackwhitelist):
    assert keyorder is None or isinstance(
        keyorder, list
    ), keyorder  # TODO: schema instead
    deep_structure = origin
    whitelist = blackwhitelist.get("whitelist")
    if whitelist is not None:
        assert isinstance(whitelist, list), type(whitelist)  # TODO: schema instead
        deep_structure = {k: deep_structure[k] for k in whitelist}
        keyorder = [k for k in keyorder if k in whitelist]
    blacklist = blackwhitelist.get("blacklist")
    if blacklist is not None:
        assert isinstance(blacklist, list), type(blacklist)  # TODO: schema instead
        deep_structure = {
            k: deep_structure[k] for k in deep_structure if k not in blacklist
        }
        keyorder = [k for k in keyorder if k not in blacklist]
    return deep_structure, keyorder


def _translate_deep(node, root, namespace, inchannels, outchannels, *, hash_pattern):
    # TODO: set schemas for keyorder, blacklist, whitelist
    from .translate import set_structured_cell_from_checksum

    for inchannel in inchannels:
        if inchannel not in ((), ("blacklist",), ("whitelist",), None):
            raise AssertionError  # inchannels not allowed, unless black/whitelist or complete assignment

    path = node["path"]

    parent = get_path(root, path[:-1], None, None)
    name = path[-1]
    ctx = context(toplevel=False)
    setattr(parent, name, ctx)

    real_inchannels = [
        ic for ic in inchannels if ic not in (("blacklist",), ("whitelist",))
    ]
    ctx.origin = build_structured_cell(
        parent,
        name + "_ORIGIN",
        real_inchannels,
        [()],
        fingertip_no_remote=node.get("fingertip_no_remote", False),
        fingertip_no_recompute=node.get("fingertip_no_recompute", False),
        hash_pattern=hash_pattern,
    )
    ctx.filtered = build_structured_cell(
        parent,
        name + "_FILTERED",
        [()],
        outchannels,
        fingertip_no_remote=node.get("fingertip_no_remote", False),
        fingertip_no_recompute=node.get("fingertip_no_recompute", False),
        hash_pattern=hash_pattern,
    )

    checksum = node.get("checksum")
    if checksum is not None:
        set_structured_cell_from_checksum(ctx.origin, checksum, is_deepcell=True)
    else:
        checksum = {}

    keyorder = core_cell("plain").set_checksum(
        checksum.get("keyorder", empty_list_checksum)
    )
    ctx.keyorder = keyorder

    ctx.filtered_keyorder = core_cell("plain")

    namespace[path, "target"] = DeepCellConnector(ctx.origin, ctx.keyorder), node
    for outchannel in outchannels:
        if outchannel == ():
            namespace[path, "source"] = (
                DeepCellConnector(ctx.filtered, ctx.filtered_keyorder),
                node,
            )
        else:
            cpath = path + outchannel
            namespace[cpath, "source"] = ctx.filtered.outchannels[outchannel], node

    ctx.origin_integrated = core_cell("mixed", hash_pattern=hash_pattern)
    ctx.keyorder_integrated = core_cell("plain")

    share = node.get("share")
    if share is not None:
        ctx.origin0 = core_cell("mixed", hash_pattern=hash_pattern)
        ctx.origin.outchannels[()].connect(ctx.origin0)
        ctx.origin02 = core_cell("checksum")
        ctx.origin0.connect(ctx.origin02)
        ctx.origin03 = core_cell("plain")
        ctx.origin02.connect(ctx.origin03)
        ctx.origin04 = core_cell("checksum")
        ctx.origin03.connect(ctx.origin04)

        ctx.options = core_cell("plain")
        ctx.options.set(share["options"])
        ctx.selected_option = core_cell("text")
        ctx.option_reactor_code = core_cell("python").set(option_reactor_code)
        reactor_params = {
            "origin": {"io": "input", "celltype": "checksum"},
            "keyorder": {"io": "input", "celltype": "checksum"},
            "options": {
                "io": "edit",
                "must_be_defined": False,
            },  # actually an input pin
            "selected_option": {"io": "edit", "must_be_defined": False},
            "origin_integrated0": {"io": "output", "celltype": "checksum"},
            "keyorder_integrated0": {"io": "output", "celltype": "checksum"},
        }
        ctx.integrate_options = rc = reactor(reactor_params)
        rc.code_start.cell().set(
            """
upstream = {}
options = None
selected_option = None
last_value = None
"""
        )
        ctx.option_reactor_code.connect(rc.code_update)
        rc.code_stop.cell().set("")
        ctx.origin04.connect(rc.origin)
        ctx.keyorder0 = core_cell("checksum")
        ctx.keyorder.connect(ctx.keyorder0)
        ctx.keyorder0.connect(rc.keyorder)
        ctx.options.connect(rc.options)
        ctx.selected_option.connect(rc.selected_option)
        ctx.origin_integrated0 = core_cell("checksum")
        rc.origin_integrated0.connect(ctx.origin_integrated0)
        ctx.origin_integrated0.connect(ctx.origin_integrated)
        ctx.keyorder_integrated0 = core_cell("checksum")
        rc.keyorder_integrated0.connect(ctx.keyorder_integrated0)
        ctx.keyorder_integrated0.connect(ctx.keyorder_integrated)
    else:
        ctx.origin.outchannels[()].connect(ctx.origin_integrated)
        ctx.keyorder.connect(ctx.keyorder_integrated)

    ctx.blacklist = core_cell("plain")
    ctx.whitelist = core_cell("plain")
    namespace[path + ("blacklist",), "target"] = ctx.blacklist, "target"
    namespace[path + ("whitelist",), "target"] = ctx.whitelist, "target"

    if "blacklist" in checksum:
        ctx.blacklist._set_checksum(checksum["blacklist"], initial=True)
    if "whitelist" in checksum:
        ctx.whitelist._set_checksum(checksum["whitelist"], initial=True)

    ctx.blackwhitelist = build_structured_cell(
        parent,
        name + "_BLACKWHITELIST",
        [("blacklist",), ("whitelist",)],
        [()],
        fingertip_no_remote=False,
        fingertip_no_recompute=False,
        hash_pattern=None,
    )
    empty_dict_cs = (
        "d0a1b2af1705c1b8495b00145082ef7470384e62ac1c4d9b9cdbbe0476c28f8c"  # {}
    )
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
    ctx.blackwhitelist0 = core_cell("mixed", hash_pattern={"*": "#"})
    ctx.blackwhitelist.outchannels[()].connect(ctx.blackwhitelist0)
    ctx.blackwhitelist0.connect(tf.blackwhitelist)
    ctx.keyorder_integrated.connect(tf.keyorder)
    ctx.origin_integrated.connect(tf.origin)
    tf.code.set(apply_blackwhitelist)
    ctx.filtered_all0 = core_cell("plain")
    tf.result.connect(ctx.filtered_all0)
    ctx.filtered_all = build_structured_cell(
        parent,
        name + "_FILTERED_ALL",
        [()],
        [(0,), (1,)],
        fingertip_no_remote=False,
        fingertip_no_recompute=False,
        hash_pattern=None,
    )
    ctx.filtered_all0.connect(ctx.filtered_all.inchannels[()])

    ctx.filtered_all.outchannels[(1,)].connect(ctx.filtered_keyorder)

    ctx.filtered0 = core_cell("mixed", hash_pattern=hash_pattern)
    ctx.filtered_all.outchannels[(0,)].connect(ctx.filtered0)
    ctx.filtered0.connect(ctx.filtered.inchannels[()])

    return ctx


def translate_deepcell(node, root, namespace, inchannels, outchannels):
    return _translate_deep(
        node, root, namespace, inchannels, outchannels, hash_pattern={"*": "#"}
    )


def translate_deepfoldercell(node, root, namespace, inchannels, outchannels):
    return _translate_deep(
        node, root, namespace, inchannels, outchannels, hash_pattern={"*": "##"}
    )
