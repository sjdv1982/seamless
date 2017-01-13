from seamless import macro

@macro("str")
def hiveprocess(ctx, hivename):

    from hive.ppin import PushInBee
    from hive.ppout import PushOutBee
    from hive.classes.resolve_bee import ResolveBee
    from hive.antenna import HiveAntenna
    from hive.output import HiveOutput
    from hive.attribute import Attribute
    from hive.hive import HiveObject, HiveBuilder    
    from hive.manager import hive_mode_as
    from seamless.core.editor import editor

    def hiveprocess_start():
        import hive
        myhive = hivecls()
        for attr, hivepin_type in hive_attributes.items():
            if hivepin_type == "push_out":
                output = globals()[attr]
                hive.connect(getattr(myhive, attr), hive.push_in(output.set))
        _cache["myhive"] = myhive

    def hiveprocess_update():
        myhive = _cache["myhive"]
        for attr, hivepin_type in hive_attributes.items():
            if attr not in _updated:
                continue
            value = globals()[attr]
            if hivepin_type == "attribute":
                setattr(myhive, attr, value)
            elif hivepin_type == "push_in":
                getattr(myhive, attr).push(value)

    def hiveprocess_stop():
        myhive = _cache["myhive"]
        if hasattr(myhive, "destroy"):
            myhive.destroy()
        del _cache["myhive"]


    ctx.registrar.hive.connect(hivename, ctx)
    hivecls = ctx.registrar.hive.get(hivename)
    assert issubclass(hivecls, HiveBuilder)
    with hive_mode_as("build"):
        hiveobject = hivecls() #hive must take no arguments!
    assert isinstance(hiveobject, HiveObject)
    hive_attributes = {}
    editor_params = { "hive_attributes": {"pin": "input", "dtype": "json"}}
    for attr in dir(hiveobject._hive_ex):
        hivepin = getattr(hiveobject._hive_ex, attr)
        hivepin_type = None
        if isinstance(hivepin, HiveAntenna):
            hivepin = hivepin.export()
        if isinstance(hivepin, HiveOutput):
            hivepin = hivepin.export()
        while isinstance(hivepin, ResolveBee):
            hivepin = hivepin._bee

        if isinstance(hivepin, Attribute):
            #hivepin_type = "attribute"
            #pin = "input"
            continue ### keep it like this??
        elif isinstance(hivepin, PushInBee):
            hivepin_type = "push_in"
            pin = "input"
        elif isinstance(hivepin, PushOutBee):
            hivepin_type = "push_out"
            pin = "output"
        else:
            continue

        hive_attributes[attr] = hivepin_type
        dtype = hivepin.data_type
        if dtype is None:
            dtype = "object"
        editor_params[attr] = {"pin": pin, "dtype": dtype}
    ed = ctx.ed = editor(editor_params)
    ctx.registrar.hive.connect(hivename, ed, "hivecls")
    ctx.hive_attributes = ed.hive_attributes.cell().set(hive_attributes)
    ed.code_start.cell().set(hiveprocess_start)
    ed.code_update.cell().set(hiveprocess_update)
    ed.code_stop.cell().set(hiveprocess_stop)
    ctx.export(ed)
