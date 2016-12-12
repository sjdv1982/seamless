from hive.hive import HiveObject, HiveBuilder
from hive.ppin import PushInBee
from hive.antenna import HiveAntenna
from hive.attribute import Attribute
from hive.manager import hive_mode_as
from seamless import macro
from seamless.core.editor import Editor

#TODO: update with subcontext once macros are working
#@macro("string") ###
@macro("string", with_context=False)
#def hiveprocess(ctx, hivename): ###
def hiveprocess(hivename):
    #TODO: obtain hive registrar from subcontex
    #HACK
    from seamless.core.registrar import _registrars
    hive_registrar = _registrars["hive"]
    #/HACK
    hivecls = getattr(hive_registrar, hivename)
    assert issubclass(hivecls, HiveBuilder)
    with hive_mode_as("build"):
        hiveobject = hivecls() #hive must take no arguments!
    assert isinstance(hiveobject, HiveObject)
    editor_params = {}
    for attr in dir(hiveobject._hive_ex):
        hivepin = getattr(hiveobject._hive_ex, attr)
        print(attr, isinstance(hivepin,HiveAntenna), hivepin)
        if isinstance(hivepin, HiveAntenna):
            editor_params[attr] = {"pin": "input", "dtype": "object"}
        if isinstance(hivepin, Attribute):
            editor_params[attr] = {"pin": "input", "dtype": "object"}
    ed = Editor(editor_params)
    return ed
    #TODO: return subcontext
