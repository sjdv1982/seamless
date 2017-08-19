from .. import macro, reactor
from ..core.cell import Cell
from ..core.resource import load_cell

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

def link(cell, directory=None, filename=None, *,
        latency=0.2, own=False, file_dominant=False):
    """Creates a continuous link between cell and file
    ...
    latency: how often the file is polled, in seconds (default 0.2)
    file_dominant (default False):
        if False, when the context is loaded, a changed file is overwritten by the cell
        if True, when the context is loaded, a changed file overwrites the cell
    """
    import os
    assert isinstance(cell, Cell)
    if directory is not None: assert filename is not None
    assert cell.context is not None

    dtype = cell.dtype
    if dtype is not None and (dtype == "cson" or dtype[0] == "cson"):
        dtype = "text"

    if directory is None or filename is None:
        filepath = cell.resource.filepath
        if cell.resource.lib:
            import seamless
            seamless_lib_dir = os.path.realpath(
              os.path.split(seamless.lib.__file__)[0]
            )
            filepath = seamless_lib_dir + filepath
            print("WARNING: linking library file '%s'" % filepath )
    else:
        filepath = os.path.join(directory, filename)
        cell.resource.filepath = filepath
        cell.resource.lib = False
        cell.resource.mode = 5
    if cell.status() in ("UNDEFINED", "UNCONNECTED") :
        if filepath is not None and not os.path.exists(filepath):
            fh = open(filepath, "w")
            fh.close()
        elif filepath is not None:
            try:
                load_cell(cell, filepath)
            except:
                import traceback
                traceback.print_exc()

    fl = filelink(cell.dtype)
    if file_dominant:
        cell.resource.mode = 3
    fl.filepath.cell().set(filepath)
    fl.latency.cell().set(latency)
    cell.connect(fl.value)
    if own:
        cell.own(fl)
    return fl
