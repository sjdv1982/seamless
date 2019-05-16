from distutils.core import Extension
from distutils.core import Distribution
from numpy.distutils.core import Extension as NumpyExtension
from numpy.distutils.core import NumpyDistribution, numpy_cmdclass
from .cffi import _build_extension

def build_extension_cffi(binary_objects, target, c_header, link_options, compiler_verbose=False):
    # TODO: check that there is no Cython

    debug = (target == "debug")
    def distclass(**kwargs):
        return Distribution(kwargs)

    return _build_extension(
        binary_objects, c_header,
        Extension, distclass,
        link_options, compiler_verbose, debug
      )

