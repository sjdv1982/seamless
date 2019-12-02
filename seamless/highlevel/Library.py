class Library:
    def __init__(self, title):
        self._title = title
        self._library_item = None
    def __setattr__(self, attr, ctx):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, ctx)
        raise NotImplementedError ###
        """
        from .Context import Context
        assert isinstance(ctx, Context)
        ctx._from_lib = None
        libname = self._name_prefix + attr
        ctx._as_lib = _create_library_item(self, libname, attr)
        object.__setattr__(self, attr, ctx)
        ctx.translate(force=True)
        ctx.register_library()
        """


'''
class LibraryItem:
    def __init__(self, library, name, childname):
        self.library = library
        self.name = name
        self.childname = childname
        self.constructor = None
        self.copy_deps = set() # set of (weakref(Context), path)
                               # where path points to a SubContext copied from the library
        self.constructor_deps = set() # set of depsgraph items
        self.needs_update = False

    def set_constructor(self, constructor):
        assert isinstance(constructor, ConstructorItem)
        self.constructor = constructor

    def update(self, force=False):
        """Triggers an indirect library update
        Library dependencies receive a fresh copy of the library
        Their top-level contexts are then re-translated"""
        from .assign import assign_context
        if not self.needs_update and not force:
            return
        #print("LibItem UPDATE", self.name, self.copy_deps)
        lib = getattr(self.library, self.name)
        dep_ctx = []
        for dep in self.copy_deps:
            ctx_ref, path = dep
            ctx = ctx_ref()
            assign_context(ctx, path, lib)
            dep_ctx.append(ctx)
        for dep in self.constructor_deps:
            raise NotImplementedError("LibraryItem.update constructor_dep")
        for ctx in dep_ctx:
            ctx.translate()
        self.needs_update = False


_library_items = {}
def _create_library_item(library, libname, childname):
    if libname in _library_items:
        libitem = _library_items[libname]
        if library._title == libitem.library._title:
            lib1, lib2 = hex(id(library)), hex(id(libitem.library._title))
        else:
            lib1, lib2 = library._title, libitem.library._title
        raise ValueError("Library %s in %s already defined in %s" % (libname, lib1, lib2))
    libitem = LibraryItem(library, libname, childname)
    _library_items[libname] = libitem
    return libitem

def get_libitem(libname):
    return _library_items[libname]

def set_constructor(libname, constructor_code, post_constructor_code, args, direct_library_access):
    libitem = get_libitem(libname)
    constructor = ConstructorItem(libname, constructor_code, post_constructor_code, args, direct_library_access)
    libitem.set_constructor(constructor)

def get_lib_paths(ctx):
    from .Context import Context
    assert isinstance(ctx, Context)
    lib_paths = {}
    for nodepath, node in ctx._graph.nodes.items():
        if node["type"] != "context":
            continue
        from_lib = node.get("from_lib")
        if from_lib is not None:
            lib_paths[nodepath] = from_lib
'''

def register_library(*args, **kwargs):
    raise NotImplementedError
    # Also update depsgraph!

stdlib = Library(title="stdlib")
mylib = Library(title="mylib")
