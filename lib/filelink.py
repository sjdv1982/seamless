from seamless import macro, editor
from seamless.core.cell import Cell

#TODO: support for no-filename invocations (obtain filepath from resource API)
#TODO: special-case seamless standard library cells (use resource/libmanager API)

@macro("str")
def filelink(ctx, cell_type):
    from seamless import editor
    pinparams = {
       "value": {
         "pin": "edit",
         "dtype": cell_type
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
    ed.code_start.cell().fromfile("cell-filelink-start.py")
    ed.code_update.cell().set("write_file(filepath.get())")
    ed.code_stop.cell().set('t.join(0)')
    ctx.export(ed)

def link(cell, directory, filename, latency=0.2, own=False):
    import os
    assert isinstance(cell, Cell)
    assert cell.context is not None
    filepath = os.path.join(directory, filename)
    fl = filelink(cell.dtype)
    fl.filepath.cell().set(filepath)
    fl.latency.cell().set(latency)
    cell.connect(fl.value)
    if own:
        cell.own(fl)
    fl._validate_path()
    return fl
