import inspect
import weakref
import os
import inspect
import importlib
from . import libmanager

class Resource:
    """
    Describes the relation between a cell and a named resource, typically a
     file on disk.
    Note that this relationship is only in effect upon saving and loading of
     the context. To create real-time dynamic relationships, use filelink()
     in the standard library

    Attributes:
    - filename: the file the cell is linked to
    - lib: True if the cell is a standard library cell
    - mode:
    The following modes are available

    1: The cell is completely dependent on the file. Cell data is not stored
     when the context is saved. When the context is loaded and the file is not
     present, an exception is raised.

    2: The cell is dependent on the file. Cell data is stored when the context
     is saved. When the context is loaded and the file is present, the cell data
     is updated with the contents of the file.
     This is the default for standard library cells.

    3: As above, but when the context is loaded and the file is not present,
     the file is created and filled with the cell data contents.

    4: File and cell are not dependent of each other. Cell data is stored when
     the context is saved. When the context is loaded, if the file is present,
     and if the file contents are different from the cell data, a warning is
     printed.

    5: As above, but filelinks can be created without filename argument
     to modify the file on disk.
     This is the default for standard cells

    6: The file is dependent on the cell. Filelinks can be created without
     filename argument to modify the file on disk.
     Whenever the context is saved, the file is checked. If the file does not
     exist, or has different content than the cell data, the cell data is
     written to the file.

    TODO: implement these modes
    TODO: define enum constants

    In addition, if the cell belongs to the standard library,
     the Resource class takes care of the communication with the libmanager
    """
    filename = None
    lib = None
    mode = None
    cache = None
    """cache can have the following modes:
    - None: the cell is undefined
    - False: the cell has been set with an arbitrary value, from code or from edit
    - True: the cell is dependent and has been set from its upstream transformer
    - a string: the cell has been set using .fromfile(), the string indicates the file name
    """
    def __init__(self, parent):
        self.parent = weakref.ref(parent)

    def fromfile(self, filename, frames_back):
        cell = self.parent()
        from .macro import get_macro_mode
        import seamless
        old_filename = self.filename
        old_lib = self.lib
        if get_macro_mode():
            #TODO: this duplicates code from libmanager
            x = inspect.currentframe()
            for n in range(frames_back):
                x = x.f_back
            caller_filename = x.f_code.co_filename
            if caller_filename.startswith("macro <= "):
                caller_modulename = caller_filename.split(" <= ")[1]
                mod = importlib.import_module(caller_modulename )
                caller_filename = inspect.getsourcefile(mod)
            caller_filename = os.path.realpath(caller_filename)
            caller_filedir = os.path.split(caller_filename)[0]
            seamless_lib_dir = os.path.realpath(
              os.path.split(seamless.lib.__file__)[0]
            )
            if caller_filedir.startswith(seamless_lib_dir):
                sub_filedir = caller_filedir[len(seamless_lib_dir):]
                sub_filedir = sub_filedir.replace(os.sep, "/")
                new_filename = sub_filedir + "/" + filename
                if old_lib and new_filename == old_filename:
                    old_lib = False #nothing changes
                else:
                    result = libmanager.fromfile(cell, new_filename)
                self.filename = new_filename
                self.lib = True
                self.mode = 2
            else:
                new_filename = caller_filedir + os.sep + filename
                result = cell.set(open(new_filename, encoding="utf8").read())
                self.filename = new_filename
                self.lib = False
                self.mode = 5
        else:
            result = cell.set(open(filename, encoding="utf8").read())
            self.filename = filename
            self.lib = False
            self.mode = 5
        if old_lib:
            libmanager.on_cell_destroy(self.parent(), old_filename)
        self.cache = self.filename
        return result

    def fromlibfile(self, lib, filename):
        cell = self.parent()
        if inspect.ismodule(lib):
            mod = lib
        else:
            mod = importlib.import_module(lib)
        modfilename = inspect.getsourcefile(mod)
        modfilename = os.path.realpath(modfilename)
        mod_dir = os.path.split(modfilename)[0]
        new_filename = mod_dir + os.sep + filename
        result = cell.set(open(new_filename, encoding="utf8").read())
        self.filename = new_filename
        self.cache = self.filename
        self.lib = False
        self.mode = 5
        return result

    def update(self):
        #TODO: other modes
        from .libmanager import _lib
        parent = self.parent()
        if parent is None:
            return
        if self.lib:
            if self.mode <= 3:
                if self.filename in _lib:
                    lib_data = _lib[self.filename]
                    current_data = parent.data
                    if lib_data != current_data:
                        print("Updating %s from lib filename %s" % (parent, self.filename))
                        parent.set(lib_data)
                        current_data = parent.data
                        self.cache = self.filename

    def destroy(self):
        if self.lib:
            libmanager.on_cell_destroy(self.parent(), self.filename)
