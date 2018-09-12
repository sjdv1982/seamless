"""
Two mechanisms of library update:
- Direct library update.
  This uses low-level library registration.
  Whenever an authoritative, non-slave changes ctx, any libcell is directly updated.
- Indirect library update (high level)
  The high-level keeps track of all high-level macros that copy a library from stdlib.
  Whenever the library is re-translated or its constructor/copier changes, then
   the high-level macro is re-executed
"""
class Library:
    def __init__(self, title, name_prefix):
        self._title = title
        self._name_prefix = name_prefix
    def __setattr__(self, attr, ctx):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, ctx)
        from .Context import Context
        assert isinstance(ctx, Context)
        ctx._from_lib = None
        libname = self._name_prefix + attr
        ctx._as_lib = create_library_item(self, libname)
        object.__setattr__(self, attr, ctx)
        ctx.translate(force=True)
        ctx.register_library()

class LibraryItem:
    def __init__(self, library, name):
        self.library = library
        self.name = name
        self.copy_deps = set() # set of (weakref(Context), path)
                               # where path points to a SubContext copied from the library
        self.macro_deps = set() # set of (weakref(Context), path, arg)
                               # where path points to a Macro with the library as argument arg
        # set of paths to partial-authority StructuredCells
        # Any assignment to those paths must lead to an indirect library update
        self.partial_authority = set()
        self.needs_update = False

    def update(self):
        """Triggers an indirect library update
        Library dependencies receive a fresh copy of the library
        Their top-level contexts are then re-translated"""
        from .assign import assign_context
        if not self.needs_update:
            return
        #print("LibItem UPDATE", self.name, self.copy_deps)
        lib = getattr(self.library, self.name)
        dep_ctx = []
        for dep in self.copy_deps:
            ctx_ref, path = dep
            ctx = ctx_ref()
            assign_context(ctx, path, lib)
            dep_ctx.append(ctx)
        for dep in self.macro_deps:
            raise NotImplementedError("LibraryItem.update macro_dep")
        for ctx in dep_ctx:
            ctx.translate()
        self.needs_update = False


_library_items = {}
def create_library_item(library, libname):
    if libname in _library_items:
        libitem = _library_items[libname]
        if library._title == libitem.library._title:
            lib1, lib2 = hex(id(library)), hex(id(libitem.library._title))
        else:
            lib1, lib2 = library._title, libitem.library._title
        raise ValueError("Library %s in %s already defined in %s" % (libname, lib1, lib2))
    libitem = LibraryItem(library, libname)
    _library_items[libname] = libitem
    return libitem

def get_libitem(libname):
    return _library_items[libname]

def get_lib_paths(ctx):
    from .Context import Context
    assert isinstance(ctx, Context)
    lib_paths = {}
    for subcontext, sub in ctx._graph.subcontexts.items():
        from_lib = sub.get("from_lib")
        if from_lib is not None:
            lib_paths[subcontext] = from_lib
    return lib_paths

def check_lib_core(ctx, obj):
    """Check that a core object does not point to an authoritative cell imported from a library"""
    from ..core import SeamlessBase
    from ..core.library import lib_has_path
    assert isinstance(obj, SeamlessBase)
    lib_paths = get_lib_paths(ctx)
    objpath = obj.path
    for lib_path in lib_paths:
        if objpath[:len(lib_path)] != lib_path:
            continue
        libname = lib_paths[lib_path]
        tail = objpath[len(lib_path):]
        p = ".".join(tail)
        assert not lib_has_path(libname, p)

stdlib = Library(title="stdlib", name_prefix="")
