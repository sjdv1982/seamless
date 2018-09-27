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
        ctx._as_lib = _create_library_item(self, libname, attr)
        object.__setattr__(self, attr, ctx)
        ctx.translate(force=True)
        ctx.register_library()
    def touch(self, attr_or_context):
        """Re-evaluates all constructor dependencies
        This is meant for a libraries where direct library update has been
        disabled by the constructor, or otherwise some bug has happened"""
        if isinstance(attr_or_context, str):
            attr = attr_or_context
            ctx = getattr(self, attr)
        else:
            ctx = attr_or_context
        assert isinstance(ctx, Context) and ctx._as_lib.library is self
        raise NotImplementedError


class ConstructorItem:
    constructor = None
    post_constructor = None
    args = None
    def __init__(self,
          identifier,  #the identifier given to the code, for debugging
          constructor, #constructor (code or function object)
          post_constructor, #post-constructor, for after the context has been attached
          args, #for each arg, define "name" and the flags "as_cell" and "auth"
          direct_library_access, #True if the (post-)constructor does not create, rename or modify cell values.
                                 #Adding/deleting connections and deleting cells is OK.
        ):
        from . import parse_function_code
        # TODO: use Silk schema
        if constructor is not None:
            identifier2 = identifier + ".constructor"
            self.constructor_code, func_name, code_object = parse_function_code(constructor, identifier2)
            if func_name == "<lambda>":
                constructor_func = eval(code_object)
            else:
                ns = {}
                exec(code_object, ns)
                constructor_func = ns[func_name]
            assert callable(constructor_func)
            self.constructor = constructor_func
        elif post_constructor is not None:
            identifier2 = identifier + ".post_constructor"
            self.post_constructor_code, func_name, code_object = parse_function_code(post_constructor, identifier2)
            if func_name == "<lambda>":
                post_constructor_func = eval(code_object)
            else:
                ns = {}
                exec(code_object, ns)
                post_constructor_func = ns[func_name]
            assert callable(post_constructor_func)
            self.post_constructor = post_constructor_func
        else:
            raise ValueError("constructor or post_constructor must be defined")

        assert isinstance(args, (list, tuple))
        a = []
        names = set()
        for arg in args:
            assert isinstance(arg, dict)
            assert "name" in arg, arg
            assert arg["name"] not in names, arg["name"] #duplicate argument name
            assert "as_cell" in arg and arg["as_cell"] in (True, False), arg
            assert "auth" in arg and arg["auth"] in (True, False), arg
            assert arg["auth"] or arg["as_cell"], arg
            a.append(arg)
        self.args = tuple(a)
        self.direct_library_access = direct_library_access

    def parse_args(self, args, kwargs):
        from .Cell import Cell
        from ..mixed.get_form import get_form
        result = {}
        args_by_name = {a["name"]: a for a in self.args}
        #TODO: use Python function arg matching machinery
        all_args = [(self.args[anr], a) for anr, a in enumerate(args)] #IndexError means too many args
        all_args += [(args_by_name[aname], a) for aname, a in kwargs.items()] #KeyError means unknown keyword arg
        for tmpl, a in all_args:
            parsed_arg = {}
            name = tmpl["name"]
            assert name not in parsed_arg, name #duplicate arg
            if isinstance(a, Cell):
                is_path = True
                a = a._path
                auth = tmpl["auth"]
            else:
                try:
                    get_form(a)
                except:
                    raise ValueError("argument %s is not JSON or mixed" % name)
                assert not tmpl["as_cell"], name #value passed for cell argument
                is_path = False
                auth = True
            parsed_arg["value"] = a
            parsed_arg["is_path"] = is_path
            parsed_arg["as_cell"] = tmpl["as_cell"]
            parsed_arg["auth"] = auth
            result[name] = parsed_arg
        return result


class LibraryItem:
    def __init__(self, library, name, childname):
        self.library = library
        self.name = name
        self.childname = childname
        self.constructor = None
        self.copy_deps = set() # set of (weakref(Context), path)
                               # where path points to a SubContext copied from the library
        self.constructor_deps = set() # set of depsgraph items

        # set of paths to partial-authority StructuredCells
        # Any assignment to those paths must lead to an indirect library update
        self.partial_authority = set()
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
    return lib_paths

def test_lib_lowlevel(ctx, obj):
    """Test if a low-level object points to an authoritative cell imported from a library"""
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
        if lib_has_path(libname, p):
            return True
    return False

stdlib = Library(title="stdlib", name_prefix="")
mylib = Library(title="mylib", name_prefix="mylib__")
