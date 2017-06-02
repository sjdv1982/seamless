import os, inspect

_lib = {}
_links = {}

from .. import lib as lib_module
seamless_lib_dir = os.path.realpath(os.path.split(lib_module.__file__)[0])

def fromfile(cell, filename):
    from .. import lib as lib_module
    if filename in _lib:
        data = _lib[filename]
    else:
        new_filename = seamless_lib_dir + filename
        data = open(new_filename, encoding="utf8").read()
        _lib[filename] = data
        _links[filename] = []
    _links[filename].append(cell)
    return cell.set(data)

def update(filename, data, to_disk):
    assert filename in _lib, filename
    _lib[filename] = data
    if to_disk:
        try:
            open(filename, "w").write(data)
        except Exception:
            print("Cannot write to {0}".format(filename))
    for cell in _links[filename]:
        try:
            cell.set(data)
        except Exception:
            pass #exceptions will be reported in another manner

def on_cell_destroy(cell, filename):
    assert filename in _links, filename
    assert cell in _links[filename]
    _links[filename].remove(cell)

frames_back = 1
def load(filename, reload=False):
    x = inspect.currentframe()
    for n in range(frames_back):
        x = x.f_back
    caller_filename = x.f_code.co_filename
    if caller_filename.startswith("macro <= "):
        caller_filename = caller_filename.split(" <= ")[1]
    caller_filename = os.path.realpath(caller_filename)
    caller_filedir = os.path.split(caller_filename)[0]
    assert caller_filedir.startswith(seamless_lib_dir)
    sub_filedir = caller_filedir[len(seamless_lib_dir):]
    sub_filedir = sub_filedir.replace(os.sep, "/")
    lib_filename = sub_filedir + "/" + filename
    if not reload and lib_filename in _lib:
        return
    filepath = seamless_lib_dir + os.sep + lib_filename.replace("/", os.sep)
    data = open(filepath, encoding="utf8").read()
    _lib[lib_filename] = data
    if lib_filename not in _links:
        _links[lib_filename] = []
