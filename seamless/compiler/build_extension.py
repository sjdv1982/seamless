from distutils.core import Extension
from distutils.core import Distribution
from numpy.distutils.core import Extension as NumpyExtension
from numpy.distutils.core import NumpyDistribution, numpy_cmdclass
from .cffi import _build_extension

def build_extension_cffi(binary_module, compiler_verbose=False):
    # TODO: check that there is no Cython
    debug = (binary_module.get("target", "profile") == "debug")
    def distclass(**kwargs):
        return Distribution(kwargs)

    cffi_header = None
    public_header = binary_module["public_header"]
    assert public_header["language"] == "c"
    cffi_header = public_header["code"]
    return _build_extension(
        binary_module, cffi_header,
        Extension, distclass,
        compiler_verbose, debug
      )

"""
TODO:
- Take out Fortran files, they will be sources
- Make sure that cffi_header is None
- To be invoked only for extension modules (main module uses CFFI marshalling for Python-language workers)
def build_extension_numpy(binary_module, compiler_verbose=False):
    debug = ...
    def distclass(**kwargs):
        kwargs2 = kwargs.copy()
        kwargs2["cmdclass"] = numpy_cmdclass
        return NumpyDistribution(kwargs2)

    return _build_extension(
        binary_module, None,
        NumpyExtension, distclass,
        compiler_verbose, debug
      )
"""
