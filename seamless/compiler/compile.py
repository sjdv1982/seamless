
from . import compilers, languages
from .. import subprocess

import numpy as np
import os
from copy import deepcopy
from ..get_hash import get_hash
import shutil

from threading import RLock
from .locks import locks, locklock

cache = {}

def compile(moduletree, build_dir, compiler_verbose=False):
    """Takes a JSON dict of source module definitions (source code strings, language
    property, compiler options, etc.)
     and generates a dict-of-binary-objects (.o / .obj)
    Linking options etc. are passed through.
    This dict can be sent to a transformer or reactor over a binarymodule pin"""

    #TODO: first write all headers to disk. For now, no project headers can be used
    # (i.e. no #include "foo.h"; only library headers can be included with #include <foo>)
    binary_moduletree = deepcopy(moduletree)
    binary_moduletree["objects"] = {}
    currdir = os.path.abspath(os.getcwd())
    build_dir = os.path.abspath(build_dir)
    try:
        with locklock:
            if build_dir not in locks:
                lock = RLock()
                locks[build_dir] = lock
            else:
                lock = locks[build_dir]
        lock.acquire()
        try:
            os.mkdir(build_dir) #must be non-existing
        except FileExistsError:
            print("WARNING: compiler build dir %s already exists... this could be trouble!" % build_dir)
        overall_target = moduletree.get("target", "profile")
        for objectname, object_ in moduletree["objects"].items():
            lang = object_["language"]
            extension = object_.get("extension")
            _, language, extension2 = find_language(lang)
            if extension is None and extension2 is not None:
                extension = extension2

            compiler_name = object_.get("compiler", language.get("compiler"))
            assert compiler_name is not None, lang
            compiler = compilers[compiler_name]
            target = object_.get("target", overall_target)
            assert target in ("release", "debug", "profile"), target
            std_options = object_.get("options", compiler["options"])
            profile_options = object_.get("profile_options", compiler["profile_options"])
            debug_options = object_.get("debug_options", compiler["debug_options"])
            if target in ("release", "profile"):
                options = list(std_options)
                if target == "profile":
                    profile_options = list(profile_options) if isinstance(profile_options, str) else profile_options
                    options += profile_options
            else:
                options = list(debug_options)
            compiler_binary = compiler.get("location", compiler_name)
            if "code" not in object_:
                raise Exception("Binary Module %s: no code in object" % objectname)
            code = object_["code"]
            if extension is None:
                extension = language["extension"]
            if isinstance(extension, list):
                extension = extension[0]
            code_file = objectname + "." + extension
            code_file = os.path.join(build_dir, code_file)
            obj_file = objectname + ".o" #TODO: Windows
            obj_file = os.path.join(build_dir, obj_file)
            cmd = [compiler_binary, compiler["compile_flag"], code_file]
            cmd += options
            cmd += [compiler["output_flag"], obj_file]
            checksum = get_hash(code, hex=True)
            cachekey = (tuple(cmd), checksum)
            #TODO: include header checksums as well
            obj_array = cache.get(cachekey)
            if obj_array is None:
                with open(code_file, "w") as f:
                    f.write(code)
                cmd2 = " ".join(cmd)
                if compiler_verbose:
                    print(cmd2)
                process = subprocess.run(cmd2,shell=True, capture_output=True)
                #TODO: compilation in parallel
                print(process.stderr.decode())
                assert process.returncode == 0
                with open(obj_file, "rb") as f:
                    obj = f.read()
                obj_array = np.frombuffer(obj, dtype=np.uint8)
                cache[cachekey] = obj_array
            binary_moduletree["objects"][objectname] = (obj_array, checksum)
    finally:
        try:
            shutil.rmtree(build_dir) #TODO: sometimes skip, for GDB
        except:
            pass
        lock.release()

    return binary_moduletree

from . import find_language
