import inspect
import textwrap
import copy


def bootstrap(module):
    import inspect
    from seamless.util import strip_decorators

    result = {}
    for objname, obj in sorted(module.__dict__.items()):
        if objname.startswith("__"):
            continue
        if isinstance(obj, (int, str, float, bool, list, dict)):
            result[objname] = objname
        elif inspect.isclass(obj):
            continue
        elif inspect.ismodule(obj):
            result[objname] = bootstrap(obj)
        elif inspect.isfunction(obj):
            code = inspect.getsource(obj)
            code = textwrap.dedent(code)
            code = strip_decorators(code)
            result[objname] = code
        else:
            continue
    return result


def build_codeblock(module):
    from seamless.util import strip_decorators

    result = ""
    for objname, obj in sorted(module.__dict__.items()):
        if objname.startswith("__"):
            continue
        if isinstance(obj, (int, str, float, bool, list, dict)):
            continue
        elif inspect.isclass(obj):
            continue
        elif inspect.ismodule(obj):
            subresult = build_codeblock(obj)
            if len(subresult):
                result += "\n" + subresult
        elif inspect.isfunction(obj):
            code = inspect.getsource(obj)
            code = textwrap.dedent(code)
            code = strip_decorators(code)
            result += "\n" + code
        else:
            continue
    return result


if __name__ == "__main__":
    from seamless.workflow import Context, Cell
    import lib
    import constructors.map_list_N
    import constructors.map_list
    import constructors.map_dict
    import constructors.map_dict_chunk

    lib_module_dict = bootstrap(lib)
    lib_codeblock = build_codeblock(lib)

    ctx0 = Context()
    ctx0.lib_module_dict = Cell("plain").set(lib_module_dict)
    ctx0.lib_codeblock = Cell("plain").set(lib_codeblock)

    contexts = {}

    from seamless.workflow.highlevel.library import LibraryContainer

    mylib = LibraryContainer("mylib")

    mylib.map_list = ctx0
    mylib.map_list.constructor = constructors.map_list.constructor
    mylib.map_list.params = constructors.map_list.constructor_params

    mylib.map_list_N = ctx0
    mylib.map_list_N.constructor = constructors.map_list_N.constructor
    mylib.map_list_N.params = constructors.map_list_N.constructor_params

    mylib.map_dict = ctx0
    mylib.map_dict.constructor = constructors.map_dict.constructor
    mylib.map_dict.params = constructors.map_dict.constructor_params

    mylib.map_dict_chunk = ctx0
    mylib.map_dict_chunk.constructor = constructors.map_dict_chunk.constructor
    mylib.map_dict_chunk.params = constructors.map_dict_chunk.constructor_params

    from testing import test

    ctx = test(mylib)

    libctx = Context()
    for attr in ("map_list", "map_list_N", "map_dict", "map_dict_chunk"):
        setattr(libctx, attr, Context())
        l = getattr(libctx, attr)
        ctx00 = copy.copy(ctx0)
        ctx00.help = Cell("text")
        ctx00.help.mimetype = "md"
        ctx00.help.set(open("help/{}.md".format(attr)).read())
        l.static = ctx00
        l.constructor_code = Cell("code").set(getattr(constructors, attr).constructor)
        l.constructor_params = getattr(constructors, attr).constructor_params
    libctx.compute()
    graph = libctx.get_graph()

    import os, json

    currdir = os.path.dirname(os.path.abspath(__file__))
    graph_filename = os.path.join(currdir, "../lib-map.seamless")
    zip_filename = os.path.join(currdir, "../lib-map.zip")
    libctx.save_graph(graph_filename)
    libctx.save_zip(zip_filename)
