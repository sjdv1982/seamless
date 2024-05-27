from distutils.core import Extension
from distutils.core import Distribution

def build_extension_cffi(
    full_module_name,
    binary_objects, target, c_header, link_options, compiler_verbose=False
):
    # TODO: check that there is no Cython
    from .cffi import _build_extension

    debug = (target == "debug")
    def distclass(**kwargs):
        return Distribution(kwargs)

    return _build_extension(
        full_module_name,
        binary_objects, c_header,
        Extension, distclass,
        link_options, compiler_verbose, debug
      )

