import os, sys, io, tempfile
try:
    from cffi import FFI    
    from cffi.recompiler import Recompiler
except ImportError:
    FFI = None
    Recompiler = None
try:
    from cffi.ffiplatform import _hack_at_distutils
except ImportError:
    pass    
import distutils

import json
import importlib
import shutil

from threading import RLock
from .locks import locks, locklock

def cffi(module_name, c_header):
  """Generates CFFI C source for given C header"""
  if FFI is None or Recompiler is None:
    raise ImportError("cffi")
  ffibuilder = FFI()
  # Use the header twice:-
  ffibuilder.cdef(c_header) # once for the declaration of exported code...

  recompiler = Recompiler(ffibuilder, module_name, target_is_python=False)
  recompiler.collect_type_table()
  recompiler.collect_step_tables()
  f = io.StringIO()
  # ... and once for the internal declaration.
  # In this case, "stdbool" needs to be added
  header = '#include "stdbool.h"\n' + c_header
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
        return f.read()

def _write_objects(binary_objects, tempdir):
    objects = []
    for objfile, objdata in binary_objects.items():
        objfile = os.path.join(tempdir, objfile)
        with open(objfile, "wb") as f:
            f.write(objdata)
        objects.append(objfile)
    return objects

def _create_extension(binary_objects, full_module_name, c_header, extclass, link_options, tempdir):
    objects = _write_objects(binary_objects, tempdir)
    sources = []
    if c_header is not None:
        cffi_wrapper = cffi(full_module_name, c_header)
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
        extra_link_args = link_options,
    )
    return ext

def _build_extension(
    full_module_name, binary_objects, c_header,
    extclass, distclass, link_options,
    compiler_verbose=False, debug=None
  ):    
    currdir = os.getcwd()
    tempdir = os.path.join(tempfile.gettempdir(), "_cffi-" + full_module_name)
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
        ext = _create_extension(
          binary_objects, full_module_name, c_header, extclass, 
          link_options, tempdir
        )
        dist = distclass(ext_modules = [ext])
        extension_code = _build(dist, tempdir, compiler_verbose, debug)
    finally:
        try:
            pass # skip this for now, since cluster deployment gives troubles with it....
            ###shutil.rmtree(tempdir) #skip, for GDB
        except Exception:
            pass
        lock.release()
        os.chdir(d)
    return extension_code
