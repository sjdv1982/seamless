from .context import Context
from .reactor import Reactor
from .transformer import Transformer
from .cell import Cell, cell as cell_factory
from .macro import activation_mode_as
import json
from collections import OrderedDict
from contextlib import contextmanager

_fromfile_mode = False

def get_fromfile_mode():
    return _fromfile_mode

def set_fromfile_mode(fromfile_mode):
    global _fromfile_mode
    _fromfile_mode = fromfile_mode


@contextmanager
def fromfile_mode_as(mode):
    original_mode = get_fromfile_mode()
    set_fromfile_mode(mode)
    try:
        yield
    finally:
        set_fromfile_mode(original_mode)

def _get_sl(parent, path):
    if len(path) == 0:
        return parent
    child = getattr(parent, path[0])
    return _get_sl(child, path[1:])

def find_sl(ctx, path):
    path2 = path.split(".")
    return _get_sl(ctx, path2)

from .fromfile_manager import json_to_connections, json_to_registrar_items, \
 json_to_macro_objects, json_to_macro_listeners, json_to_registrar_cells, \
 json_to_registrar_listeners
from .fromfile_caching import fromfile_caching_ctx


def json_to_lib(data):
    #TODO: check for version conflicts; for now, don't overwrite lib
    links = OrderedDict()
    from .libmanager import _lib
    for filename in sorted(data.keys()):
        d = data[filename]
        dat = d["data"]
        if filename not in _lib: #TODO
            _lib[filename] = dat
        links[filename] = d["links"]
    return links

def links_to_lib(ctx, links):
    from .libmanager import _links
    for filename in links:
        if filename not in _links:
            _links[filename] = []
        for target in links[filename]:
            _links[filename].append(find_sl(ctx, target))

def json_to_macros(ctx, data):
    from .macro import Macro, _macros
    for m in data:
        key = m["module_name"],  m["func_name"]
        assert tuple(m["dtype"]) == Macro.dtype, (m["dtype"] , Macro.dtype)
        ta = m["type_args"]
        if isinstance(ta, list):
            ta = tuple(ta)
        macro = Macro(
          with_context=m["with_context"],
          with_caching=m.get("with_caching", False),
          type=ta,
        )
        macro.module_name=m["module_name"]
        macro.func_name=m["func_name"]
        macro.update_code(m["code"])
        _macros[key] = macro

def json_to_registrar_object(ctx, data, myname):
    registrar = getattr(ctx.registrar, data["registrar"])._registrar
    ro = registrar._registrar_object_class(
        registrar,
        data["registered"],
        data["data"],
        data["data_name"]
    )

    ctx._add_child(myname, ro)
    #ro.registrar.register(data["data"], name=data["data_name"])
    #ro.registrar.register(data["data"])
    ro.re_register(data["data"])

def json_to_cell(ctx, data, myname, ownerdict):
    dtype = data["dtype"]
    if isinstance(dtype, list):
        dtype = tuple(dtype)
    cell = cell_factory(dtype)
    if "data" in data:
        #if dtype == "json":
        #    import seamless.dtypes
        #    assert isinstance(seamless.dtypes.parse("json", data["data"],  False), (dict,list,str,int,float,None))
        cell.set(data["data"])
    if "hash" in data:
        cell.resource._hash = data["hash"]
    if "store" in data:
        cell.set_store(data["store"]["mode"],
                       **data["store"]["params"])

    ctx._add_child(myname, cell)

    if "resource" in data:
        d = data["resource"]
        r = cell.resource
        r.mode = d["mode"]
        r.lib = d["lib"] #NOTE: link will already be created in links_to_lib!
        r.filepath = d["filepath"]
        sp = d.get("save_policy", None)
        if sp is not None:
            r.save_policy = sp
        r.update()

    owner = data.get("owner", None)
    if owner is not None:
        ownerdict[cell] = owner

def json_to_worker(ctx, data, myname, ownerdict):
    if data["type"] == "reactor":
        assert data["mode"] == "sync", data["mode"]
        params = data["params"]
        child = Reactor(params)
    elif data["type"] == "transformer":
        assert data["mode"] == "thread", data["mode"]
        params = data["params"]
        child = Transformer(params)
    else:
        raise TypeError(data["type"])
    ctx._add_child(myname, child)

    owner = data.get("owner", None)
    if owner is not None:
        ownerdict[child] = owner

def json_to_ctx(ctx, data, myname=None, ownerdict=None, pinlist=None):

    from .worker import InputPinBase, ExportedInputPin, \
      OutputPinBase, ExportedOutputPin, \
      EditPinBase, ExportedEditPin

    if myname is None:
        myctx = ctx
        assert ownerdict is None
        assert pinlist is None
        ownerdict = OrderedDict()
        pinlist = []
    else:
        myctx = Context(context=ctx,active_context=False)
        assert ownerdict is not None
        assert pinlist is not None

    myctx._like_worker = data["like_worker"]
    myctx._like_cell = data["like_cell"]
    myctx._auto = set(data["auto"])
    if myname is not None:
        ctx._add_child(myname, myctx)
    for childname, c in sorted(data["children"].items()):
        if "type" not in c:
            if "registrar" in c:
                json_to_registrar_object(myctx, c, childname)
            else:
                json_to_cell(myctx, c, childname, ownerdict)
        elif c["type"] in ("reactor", "transformer"):
            json_to_worker(myctx, c, childname, ownerdict)
        elif c["type"] == "context":
            json_to_ctx(myctx, c, childname, ownerdict, pinlist)

    owner = data.get("owner", None)
    if owner is not None:
        ownerdict[myctx] = owner

    if myname is None:
        for sl, ownerpath in ownerdict.items():
            owner = find_sl(ctx, ownerpath)
            owner.own(sl)

    for pinname, pinpath0 in sorted(data["pins"].items()):
        pinlist.append((myctx, pinname, pinpath0))

    if myname is None:
        for myctx, pinname, pinpath0 in pinlist:
            typename, pinpath = pinpath0
            pin = find_sl(ctx, pinpath)
            if isinstance(pin, InputPinBase):
                assert typename == "ExportedInputPin"
                myctx._pins[pinname] = ExportedInputPin(pin)
            elif isinstance(pin, OutputPinBase):
                assert typename == "ExportedOutputPin"
                myctx._pins[pinname] = ExportedOutputPin(pin)
            elif isinstance(pin, EditPinBase):
                assert typename == "ExportedEditPin"
                myctx._pins[pinname] = ExportedEditPin(pin)
            elif isinstance(pin, Cell):
                if typename == "ExportedInputPin":
                    myctx._pins[pinname] = ExportedInputPin(pin)
                elif typename == "ExportedOutputPin":
                    myctx._pins[pinname] = ExportedOutputPin(pin)
                elif typename == "ExportedEditPin":
                    myctx._pins[pinname] = ExportedEditPin(pin)
                else:
                    raise TypeError(pin, type(pin), typename)
            else:
                raise TypeError(pin, type(pin))


def fromfile(filename):
    ctx = Context()
    with fromfile_mode_as(True), \
         activation_mode_as(False), \
         fromfile_caching_ctx(ctx):
        data = json.load(open(filename))
        links = json_to_lib(data["lib"])
        m = ctx._manager
        json_to_registrar_items(ctx, m, data["main"])
        json_to_macros(ctx, data["macro"])
        json_to_ctx(ctx, data["main"])
        links_to_lib(ctx, links)
        macro_objects = json_to_macro_objects(ctx, data["main"]["macro_objects"])
        json_to_registrar_listeners(ctx, data["main"]["registrar_listeners"], macro_objects)
        json_to_macro_listeners(ctx, data["main"]["macro_listeners"], macro_objects)
        json_to_registrar_cells(ctx, data["main"]["registrar_cells"])
        json_to_connections(ctx, data["main"])
    unstable = ctx.equilibrate(5)
    if len(unstable):
        print("WARNING: Loading '%s' before making connections, could not equilibrate within 5 seconds" % filename)
    print("%s LOADED" % filename)
    return ctx
