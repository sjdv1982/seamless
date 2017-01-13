import inspect
import weakref
import os
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
    def __init__(self, parent):
        self.parent = weakref.ref(parent)

    def fromfile(self, filename, frames_back):
        cell = self.parent()
        from .macro import get_macro_mode
        import seamless
        old_filename = self.filename
        old_lib = self.lib
        if get_macro_mode():
            x =  inspect.currentframe()
            for n in range(frames_back):
                x = x.f_back
            caller_filename = x.f_code.co_filename
            if caller_filename.startswith("macro <= "):
                caller_filename = caller_filename.split(" <= ")[1]
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
                    ret = libmanager.fromfile(cell, new_filename)
                self.filename = new_filename
                self.lib = True
                self.mode = 2
            else:
                new_filename = caller_filedir + os.sep + filename
                ret = cell.set(open(new_filename).read())
                self.filename = new_filename
                self.lib = False
                self.mode = 5
        else:
            ret = cell.set(open(filename).read())
            self.filename = filename
            self.lib = False
            self.mode = 5
        if old_lib:
            libmanager.on_cell_destroy(self.parent(), old_filename)
        return self.parent()

    def destroy(self):
        if self.lib:
            libmanager.on_cell_destroy(self.parent(), self.filename)
