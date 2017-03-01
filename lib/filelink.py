from seamless import macro, editor
from seamless.core.cell import Cell

#TODO: support for no-filename invocations (obtain filepath from resource API)
#TODO: special-case seamless standard library cells (use resource/libmanager API)

cell_filelink_start = "cell-filelink-start.py"
from seamless.core import libmanager
libmanager.load(cell_filelink_start)

@macro("str")
def filelink(ctx, cell_type):
    cell_filelink_start = "cell-filelink-start.py" #repeat for inline
    from seamless import editor
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
    ed = ctx.ed = editor(pinparams)
    ed.code_start.cell().fromfile(cell_filelink_start)
    ed.code_update.cell().set("write_file(PINS.filepath.get())")
    ed.code_stop.cell().set('t.join(0)')
    ctx.export(ed)

def link(cell, directory=None, filename=None, latency=0.2, own=False):
    import os
    assert isinstance(cell, Cell)
    assert cell.context is not None
    if directory is None or filename is None:
        assert not cell.resource.lib
        filepath = cell.resource.filename
    else:
        filepath = os.path.join(directory, filename)
    if cell.status == "UNINITIALISED" and not os.path.exists(filepath):
        fh = open(filepath, "w")
        fh.close()
    fl = filelink(cell.dtype)
    fl.filepath.cell().set(filepath)
    fl.latency.cell().set(latency)
    cell.connect(fl.value)
    if own:
        cell.own(fl)
    return fl
