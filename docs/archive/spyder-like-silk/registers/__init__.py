def register(silkcode, *, doc=None, docson=None):
    """Direct register of Silk code
    completely bypasses the Seamless core"""
    import json
    from lxml import etree
    from ..typeparse import parse
    from ..transform import silkschema_to_minischema
    from ..typeparse.xmlschemaparse import get_blocks, get_init_tree
    from .minischemas import _minischemas, register_minischema
    from .typenames import register as typename_register, _silk_types

    if isinstance(silkcode, bytes):
        silkcode = silkcode.encode('UTF8')
    tree = parse(silkcode)
    silkschema = etree.tostring(tree, pretty_print=True, xml_declaration=True, encoding="UTF-8")
    minischemas = silkschema_to_minischema(silkschema)
    for minischema in minischemas:
        register_minischema(minischema)

    blocks = get_blocks(tree)
    init_trees = get_init_tree(tree)
    silktypes = []
    for silktype in blocks:
        b = blocks[silktype]
        init_tree = init_trees[silktype]
        typename_register(
            _minischemas[silktype],
            validation_blocks=b["validationblocks"],
            error_blocks=b["errorblocks"],
            method_blocks=b["methodblocks"],
            init_tree=init_tree,
        )
        silktypes.append(silktype)
    return silktypes

def unregister(silktypes):
    from .typenames import unregister as typename_unregister
    from .minischemas import _minischemas
    if isinstance(silktypes, str):
        silktypes = [silktypes]
    for silktype in silktypes:
        if silktype in _minischemas:
            _minischemas.pop(silktype)
        typename_unregister(silktype)
