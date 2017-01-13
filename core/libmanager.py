import os

_lib = {}
_links = {}

def fromfile(cell, filename):
    from .. import lib as lib_module
    if filename in _lib:
        data = _lib[filename]
    else:
        seamless_lib_dir = os.path.realpath(os.path.split(lib_module.__file__)[0])
        new_filename = seamless_lib_dir + filename
        data = open(new_filename).read()
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
        except:
            print("Cannot write to {0}".format(filename))
    for cell in _links[filename]:
        try:
            cell.set(data)
        except:
            pass #exceptions will be reported in another manner

def on_cell_destroy(cell, filename):
    assert filename in _links, filename
    assert cell in _links[filename]
    _links[filename].remove(cell)
