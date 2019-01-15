from cffi import FFI
import os, sys, io, tempfile
from cffi.ffiplatform import _hack_at_distutils
from cffi.recompiler import Recompiler

import distutils
from distutils.core import Extension
from distutils.core import Distribution
from numpy.distutils.core import Extension as NumpyExtension
from numpy.distutils.core import NumpyDistribution, numpy_cmdclass

from ..get_hash import get_hash
import json
import importlib
import shutil

from threading import RLock
from .locks import locks, locklock

SEAMLESS_EXTENSION_DIR = os.path.join(tempfile.gettempdir(), "seamless-extensions")
#  Here Seamless will write the compiled Python module .so files before importing

cache = set()

def cffi(module_name, header):
  """Generates CFFI C source for given C header"""
  ffibuilder = FFI()
  # Use the header twice:-
  ffibuilder.cdef(header) # once for the declaration of exported code...

  recompiler = Recompiler(ffibuilder, module_name, target_is_python=False)
  recompiler.collect_type_table()
  recompiler.collect_step_tables()
  f = io.StringIO()
  # ... and once for the internal declaration.
  # In this case, "stdbool" needs to be added
  header = '#include "stdbool.h"\n' + header
  recompiler.write_source_to_f(f, header)
  return f.getvalue()

def _build(dist, tempdir, compiler_verbose=False, debug=None):
    """Adapted from cffi.ffiplatform"""
    distutils.log.set_verbosity(compiler_verbose)
    dist.parse_config_files()
    options = dist.get_option_dict('build_ext')
    if debug is None:
        debug = sys.flags.debug
    options['debug'] = ('ffiplatform', debug)
    options['force'] = ('ffiplatform', True)
    options['build_lib'] = ('ffiplatform', tempdir)
    options['build_temp'] = ('ffiplatform', tempdir)
    distutils.core._setup_distribution = dist
    dist.run_command('build_ext')
    cmd_obj = dist.get_command_obj('build_ext')
    [soname] = cmd_obj.get_outputs()
    with open(soname, "rb") as f:
        soname2 = os.path.split(soname)[1]
        return soname2, f.read()

def _write_objects(binary_module, tempdir):
    objects = []
    for objectname, (obj_array, checksum) in binary_module["objects"].items():
        objdata = obj_array.tobytes()
        objfile = objectname+".o"#TODO: Windows
        objfile = os.path.join(tempdir, objfile)
        with open(objfile, "wb") as f:
            f.write(objdata)
        objects.append(objfile)
    return objects

def _prepare_extension(binary_module, cffi_header):
    merkle_tree = {}
    for objectname, (obj_array, checksum) in binary_module["objects"].items():
        merkle_tree[objectname] = checksum
    if cffi_header is not None:
        merkle_tree["_cffi_header"] = get_hash(cffi_header, hex=True)
    grand_checksum = get_hash(json.dumps(merkle_tree), hex=True)
    full_module_name = "seamless_" + grand_checksum
    return full_module_name, merkle_tree

def _create_extension(binary_module, full_module_name, cffi_header, extclass, tempdir):
    objects = _write_objects(binary_module, tempdir)
    sources = []
    if cffi_header is not None:
        cffi_wrapper = cffi(full_module_name, cffi_header)
        cffi_wrapper_name = "_cffi_wrapper_" + full_module_name
        cffi_wrapper_file0 = cffi_wrapper_name + ".c"
        cffi_wrapper_file = os.path.join(tempdir, cffi_wrapper_file0)
        with open(cffi_wrapper_file, "w") as f:
            f.write(cffi_wrapper)
    sources = [cffi_wrapper_file0]
    ext = extclass(
        name = full_module_name,
        extra_objects = objects,
        sources = sources,
        extra_link_args = binary_module.get("link_options", []),
    )
    return ext

def _build_extension(
    binary_module, cffi_header,
    extclass, distclass,
    compiler_verbose=False, debug=None
  ):
    full_module_name, _ = _prepare_extension(binary_module, cffi_header)
    if full_module_name in cache:
        return full_module_name
    currdir = os.getcwd()
    tempdir = os.path.join(tempfile.gettempdir(), "_build-" + full_module_name)
    tempdir = os.path.abspath(tempdir)
    with locklock:
        if tempdir not in locks:
            lock = RLock()
            locks[tempdir] = lock
        else:
            lock = locks[tempdir]
    try:
        lock.acquire()
        d = os.getcwd()
        try:
            os.mkdir(tempdir)
        except FileExistsError:
            shutil.rmtree(tempdir)
            os.mkdir(tempdir)
        os.chdir(tempdir)
        ext = _create_extension(binary_module, full_module_name, cffi_header, extclass, tempdir)
        dist = distclass(ext_modules = [ext])
        soname, extension_code = _build(dist, tempdir, compiler_verbose, debug)
        with locklock:
            if not os.path.exists(SEAMLESS_EXTENSION_DIR):
                os.makedirs(SEAMLESS_EXTENSION_DIR)
            module_file = os.path.join(SEAMLESS_EXTENSION_DIR, soname)
            with open(module_file, "wb") as f:
                f.write(extension_code)
            syspath_old = []
            syspath_old = sys.path[:]
            try:
                sys.path.append(SEAMLESS_EXTENSION_DIR)
                importlib.import_module(full_module_name)
            finally:
                sys.path[:] = syspath_old
        cache.add(full_module_name)
    finally:
        try:
            shutil.rmtree(tempdir) #skip, for GDB
        except:
            pass
        lock.release()
        os.chdir(d)
    return full_module_name
