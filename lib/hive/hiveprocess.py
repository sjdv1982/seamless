from hive.hive import HiveObject, HiveBuilder
from hive.ppin import PushInBee
from hive.antenna import HiveAntenna
from hive.attribute import Attribute
from hive.manager import hive_mode_as
from seamless import macro
from seamless.core.editor import editor

@macro("str")
def hiveprocess(ctx, hivename):
    print("HIVEPROCESS")
    ctx.registrar.hive.connect(hivename, ctx)
    hivecls = ctx.registrar.hive.get(hivename)
    assert issubclass(hivecls, HiveBuilder)
    with hive_mode_as("build"):
        hiveobject = hivecls() #hive must take no arguments!
    assert isinstance(hiveobject, HiveObject)
    editor_params = {}
    for attr in dir(hiveobject._hive_ex):
        hivepin = getattr(hiveobject._hive_ex, attr)
        if isinstance(hivepin, (HiveAntenna, Attribute)):
            if isinstance(hivepin, HiveAntenna):
                hivepin = hivepin.export().target
            dtype = hivepin.data_type
            if dtype is None:
                dtype = "object"
            editor_params[attr] = {"pin": "input", "dtype": dtype}
    print("HIVEPROCESS!", editor_params.keys())
    ctx.ed = editor(editor_params)
    ctx.export(ctx.ed)
