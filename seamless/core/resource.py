import inspect
import weakref
import os
import inspect
import importlib
import sys
import hashlib

def get_hash(value):
    return hashlib.md5(str(value).encode("utf-8")).hexdigest()

def load_cell(cell, filepath):
    dtype = cell.dtype
    if isinstance(dtype, tuple):
        dtype = dtype[0]
    if dtype == "object":
        value = open(filepath, "rb").read()
    else:
        value = open(filepath, encoding="utf-8").read()
    cell.set(value)


def check_cell(cell, filepath):
    data = cell._data
    if data is None:
        return None
    dtype = cell.dtype
    if isinstance(dtype, tuple):
        dtype = dtype[0]
    if dtype == "object":
        value = open(filepath, "rb").read()
    else:
        value = open(filepath, encoding="utf-8").read()
    return data == value

def write_cell(cell, filepath):
    assert cell._data is not None
    dtype = cell.dtype
    if isinstance(dtype, tuple):
        dtype = dtype[0]
    if dtype == "object":
        with open(filepath, "wb") as f:
            f.write(cell._data)
    else:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(cell._data)

    if isinstance(dtype, tuple):
        dtype = dtype[0]
    if dtype == "object":
        cell.set(open(filepath, "rb").read())
    else:
        cell.set(open(filepath, encoding="utf-8").read())

class Resource:
    """
    Describes the relation between a cell and a named resource, typically a
     file on disk.
    Note that this relationship is only in effect upon saving and loading of
     the context. To create real-time dynamic relationships, use filelink()
     in the standard library

    Attributes:
    - filepath: the file the cell is linked to
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
     the context is saved. When the context is loaded, if the file is present:
     - if the cell data are None, the file is loaded
     - else, if the file contents are different from the cell data, a warning is
     printed.

    5: As above, but filelinks can be created without filepath argument
     to modify the file on disk.
     This is the default for standard cells

    6: The file is dependent on the cell. Filelinks can be created without
     filepath argument to modify the file on disk.
     Whenever the context is saved, the file is checked. If the file does not
     exist, or has different content than the cell data, the cell data is
     written to the file.

    TODO: define enum constants

    In addition, if the cell belongs to the standard library,
     the Resource class takes care of the communication with the libmanager
    """
    filepath = None
    lib = None
    mode = None
    cache = None
    """cache can have the following modes:
    - None: the cell is undefined
    - False: the cell has been set with an arbitrary value, from code or from edit
    - True: the cell is dependent and has been set from its upstream transformer
    - a string: the cell has been set using .fromfile(), the string indicates the file name
    """
    dirty = False
    """
    dirty is only True if, on startup, the cell was overwritten from file
    """
    _save_policy = 1
    _hash = None

    def __init__(self, parent):
        self.parent = weakref.ref(parent)

    @property
    def save_policy(self):
        """Governs the saving policy if the cell is dependent
        can be:
         0 (save nothing, default)
         1 (save only hash)
         2 (save value if no filepath resource with mode > 1, and up to MAX_SAVE bytes, else save only hash)
         3 (save value if no filepath resource with mode > 1, else save only hash)
         4 (always save value)
        TODO: implement MAX_SAVE
        TODO: make enums
        """
        return self._save_policy

    @save_policy.setter
    def save_policy(self, value):
        assert value in (0,1,2,3,4) #TODO: enums
        self._save_policy = value

    def get_hash(self):
        if self._hash is None:
            parent = self.parent()
            if parent is None:
                return None
            _hash = get_hash(parent.data)
            self._hash = _hash
        return self._hash

    def fromfile(self, filepath, frames_back):
        from . import libmanager
        cell = self.parent()
        from .macro import get_macro_mode
        import seamless
        old_filepath = self.filepath
        old_lib = self.lib
        if get_macro_mode():
            #TODO: this duplicates code from libmanager
            # set filepath first to get the correct resource_name for pins
            x = inspect.currentframe()
            for n in range(frames_back):
                x = x.f_back
            caller_filepath = x.f_code.co_filename
            if caller_filepath.startswith("macro <= "):
                caller_modulename = caller_filepath.split(" <= ")[1]
                mod = importlib.import_module(caller_modulename )
                caller_filepath = inspect.getsourcefile(mod)
            caller_filepath = os.path.realpath(caller_filepath)
            caller_filedir = os.path.split(caller_filepath)[0]
            seamless_lib_dir = os.path.realpath(
              os.path.split(seamless.lib.__file__)[0]
            )
            if caller_filedir.startswith(seamless_lib_dir):
                sub_filedir = caller_filedir[len(seamless_lib_dir):]
                sub_filedir = sub_filedir.replace(os.sep, "/")
                new_filepath = sub_filedir + "/" + filepath
                self.filepath = new_filepath
                self.lib = True
                self.mode = 2
                if old_lib and new_filepath == old_filepath:
                    old_lib = False #nothing changes
                else:
                    result = libmanager.fromfile(cell, new_filepath)
            else:
                new_filepath = caller_filedir + os.sep + filepath
                self.filepath = new_filepath
                self.lib = False
                self.mode = 5
                result = cell.set(open(new_filepath, encoding="utf8").read())
        else:
            self.filepath = filepath
            self.lib = False
            self.mode = 5
            result = cell.set(open(filepath, encoding="utf8").read())
        if old_lib:
            libmanager.on_cell_destroy(self.parent(), old_filepath)
        self.cache = self.filepath
        return result

    def fromlibfile(self, lib, filepath):
        cell = self.parent()
        if inspect.ismodule(lib):
            mod = lib
        else:
            mod = importlib.import_module(lib)
        modfilepath = inspect.getsourcefile(mod)
        modfilepath = os.path.realpath(modfilepath)
        mod_dir = os.path.split(modfilepath)[0]
        new_filepath = mod_dir + os.sep + filepath
        result = cell.set(open(new_filepath, encoding="utf8").read())
        self.filepath = new_filepath
        self.cache = self.filepath
        self.lib = False
        self.mode = 5
        return result

    def update(self):
        from .libmanager import _lib
        parent = self.parent()
        if parent is None:
            return

        none = (parent._data is None)
        exists = False
        if self.lib:
            exists = (self.filepath in _lib)
        else:
            exists = self.filepath is not None and (os.path.exists(self.filepath))
        load, write, check = False, False,False
        if self.mode == 1:
            if not exists:
                msg = "File '%s' does not exist, and resource mode is 1"
                raise Exception(msg % self.filepath)
            load = True
        elif self.mode == 2:
            if exists:
                load = True
                check = True
        elif self.mode == 3:
            if none:
                if exists:
                    load = True
            else:
                if exists:
                    load = True
                    check = True
                else:
                    write = True
        elif self.mode in (4,5):
            if none:
                if exists:
                    load = True
            else:
                if exists:
                    check = True
        elif self.mode == 6:
            if not none:
                write = True
                check = True #write only if the cell and file are different

        #print("resource-update", self.mode, parent, check, load, none, exists)
        if check and not self.lib:
            same = check_cell(parent, self.filepath)
            if same == False and not write:
                msg = "WARNING, cell '%s' is different from '%s'"
                print(msg % (parent.format_path(), self.filepath),file=sys.stderr)
        if load:
            if self.lib:
                lib_data = _lib[self.filepath]
                current_data = parent.data
                if current_data is None:
                    _hash = self._hash
                    lib_hash = get_hash(lib_data)
                    same = (_hash == lib_hash)
                else:
                    same = (lib_data == current_data)
                if not same:
                    print("Updating %s from lib filepath %s" % (parent.format_path(), self.filepath))
                    parent.set(lib_data)
                    self.dirty = True
                    self.cache = self.filepath
            else:
                curr_hash = self._hash
                load_cell(parent, self.filepath) #also sets self._hash to None
                if check and same == False:
                    msg = "WARNING, cell '%s' is different from '%s'"
                    print(msg % (parent.format_path(), self.filepath),file=sys.stderr)
                    self.dirty = True
                elif curr_hash is not None:
                    new_hash = self.get_hash()
                    if new_hash != curr_hash:
                        msg = "WARNING, cell '%s' is different from '%s'"
                        print(msg % (parent.format_path(), self.filepath),file=sys.stderr)
                        self.dirty = True
        elif write:
            if not check or not (same == False):
                write_cell(parent, self.filepath)

    def destroy(self):
        from . import libmanager
        if self.lib:
            libmanager.on_cell_destroy(self.parent(), self.filepath)
