from seamless import macro, reactor
from seamless.core.cell import Cell

#TODO: support for no-filename invocations (obtain filepath from resource API)
#TODO: special-case seamless standard library cells (use resource/libmanager API)

cell_filelink_start = "cell-filelink-start.py"
from seamless.core import libmanager
libmanager.load(cell_filelink_start)

@macro("str")
def filelink(ctx, cell_type):
    cell_filelink_start = "cell-filelink-start.py" #repeat for inline
    from seamless import reactor
    pinparams = {
       "value": {
         "pin": "edit",
         "dtype": cell_type,
         "must_be_defined": False
       },
       "filepath" : {
         "pin": "input",
         "dtype": "str"
       },
       "latency" : {
         "pin": "input",
         "dtype": "float"
       },
    }
    rc = ctx.rc = reactor(pinparams)
    rc.code_start.cell().fromfile(cell_filelink_start)
    rc.code_update.cell().set("write_file(PINS.filepath.get())")
    rc.code_stop.cell().set('terminate.set(); t.join()')
    ctx.export(rc)

def link(cell, directory=None, filename=None, latency=0.2, own=False):
    import os
    assert isinstance(cell, Cell)
    if directory is not None: assert filename is not None
    assert cell.context is not None
    if directory is None or filename is None:
        filepath = cell.resource.filename
        if cell.resource.lib:
            import seamless
            seamless_lib_dir = os.path.realpath(
              os.path.split(seamless.lib.__file__)[0]
            )
            filepath = seamless_lib_dir + filepath
            print("WARNING: linking library file '%s'" % filepath )
    else:
        filepath = os.path.join(directory, filename)
    if cell.status == "UNINITIALISED" :
        if filepath is not None and not os.path.exists(filepath):
            fh = open(filepath, "w", encoding="utf-8")
            fh.close()
        elif filepath is not None:
            cell.set(open(filepath, encoding="utf-8").read())

    dtype = cell.dtype
    if dtype is not None and (dtype == "cson" or dtype[0] == "cson"):
        dtype = "text"
    fl = filelink(cell.dtype)
    fl.filepath.cell().set(filepath)
    fl.latency.cell().set(latency)
    cell.connect(fl.value)
    if own:
        cell.own(fl)
    return fl
