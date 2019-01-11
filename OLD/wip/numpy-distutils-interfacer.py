"""
WIP: Spiky mixture of cffi and Numpy distutils
attempting to mix Fortran code into cffi
doesn't work, because f2py injects its own Python wrapping
TODO: salvage bits and pieces to create a Numpy distutils interfacer
"""
from cffi import FFI
import os, sys, io
from cffi.ffiplatform import _hack_at_distutils
from cffi.recompiler import Recompiler

extension_name = 'testmodule'

ffibuilder = FFI()
header = "int _result(int a, int b);"
ffibuilder.cdef(header)

c_source = header
recompiler = Recompiler(ffibuilder, extension_name+"_cffi", target_is_python=False)
recompiler.collect_type_table()
recompiler.collect_step_tables()
f = io.StringIO()
recompiler.write_source_to_f(f, c_source)

cffi_wrapper_code = f.getvalue()
cffi_wrapper_file = "_cffi_wrapper.c"
with open(cffi_wrapper_file, "w") as f:
    f.write(cffi_wrapper_code)

main_file = "testing.cpp"
with open(main_file, "w") as f:
    f.write("""
extern "C" int myresult_(int a, int b);
extern "C" int _result(int a, int b) {
    return myresult_(a, b);
}
    """)

sub_file = "testing2.f90"
with open(sub_file, "w") as f:
    f.write("""
function myresult(a,b) result(c)
    implicit none
    integer a,b,c
    c = a + b
end function
    """)

"""
ffibuilder.set_source("testmodule", header, sources=[main_file])
ffibuilder.compile(verbose=True)
"""
from numpy.distutils.core import Extension
from numpy.distutils.core import NumpyDistribution, numpy_cmdclass
from numpy.distutils.command.build_src import build_src
ext = Extension(name = extension_name,
    #extra_compile_args = ['-O3'],
    sources = [cffi_wrapper_file, main_file, sub_file],
)

import distutils.errors, distutils.log


def build(ext, compiler_verbose=False, debug=None):
    dist = NumpyDistribution({'ext_modules': [ext], "cmdclass": numpy_cmdclass})
    #distutils.log.set_verbosity(True)
    dist.parse_config_files()
    options = dist.get_option_dict('build_ext')
    tmpdir = "."
    if debug is None:
        debug = sys.flags.debug
    options['debug'] = ('ffiplatform', debug)
    options['force'] = ('ffiplatform', True)
    options['build_lib'] = ('ffiplatform', tmpdir)
    options['build_temp'] = ('ffiplatform', tmpdir)
    distutils.core._setup_distribution = dist
    dist.run_command('build_ext')
    cmd_obj = dist.get_command_obj('build_ext')
    [soname] = cmd_obj.get_outputs()
    print(soname)

_hack_at_distutils()
saved_environ = os.environ.copy()
try:
    build(ext, debug=True)
finally:
    # workaround for a distutils bugs where some env vars can
    # become longer and longer every time it is used
    for key, value in saved_environ.items():
        if os.environ.get(key) != value:
            os.environ[key] = value

import testmodule
print(dir(testmodule))
print(testmodule.myresult(2,3))
print(testmodule.result(2,3))
print(testmodule.lib.result(2,3))
