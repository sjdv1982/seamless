
from . import compilers, languages
from .. import subprocess

import numpy as np
import os
import tempfile
from copy import deepcopy
from hashlib import md5

cache = {}

def compile(moduletree, compiler_verbose=False):
    """Takes a JSON dict of source module definitions (source code strings, language
    property, compiler options, etc.)
     and generates a dict-of-binary-objects (.o / .obj)
    Linking options etc. are passed through.
    This dict can be sent to a transformer or reactor over a binarymodule pin"""

    #TODO: first write all headers to disk. For now, no project headers can be used
    # (i.e. no #include "foo.h"; only library headers can be included with #include <foo>)
    binary_moduletree = deepcopy(moduletree)
    binary_moduletree["objects"] = {}
    for objectname, object_ in moduletree["objects"].items():
        lang = object_["language"]
        extension = object_.get("extension")
        try:
            language = languages[lang]
        except KeyError:
            ext_to_lang = {}
            for lang0, language in languages.items():
                ext = language.get("extension", [])
                if isinstance(ext, str):
                    if ext == lang:
                        break
                else:
                    if lang in ext:
                        break
            else:
                raise KeyError(lang) from None
            extension = lang

        compiler_name = object_.get("compiler", language.get("compiler"))
        assert compiler_name is not None, lang
        compiler = compilers[compiler_name]
        target = object_.get("target", "profile")
        assert target in ("release", "debug", "profile"), target
        std_options = object_.get("options", compiler["options"])
        profile_options = object_.get("profile_options", compiler["profile_options"])
        debug_options = object_.get("debug_options", compiler["debug_options"])
        if target in ("release", "profile"):
            options = std_options
            options = list(options) if isinstance(options, str) else options
            if target == "profile":
                profile_options = list(profile_options) if isinstance(profile_options, str) else profile_options
                options += profile_options
        else:
            options = debug_options
            options = list(options) if isinstance(options, str) else options
        compiler_binary = compiler.get("location", compiler_name)
        code = object_["code"]
        if extension is None:
            extension = language["extension"]
        if isinstance(extension, list):
            extension = extension[0]
        code_file = objectname + "." + extension
        obj_file = objectname + ".o" #TODO: Windows
        cmd = [compiler_binary, compiler["compile_flag"], code_file]
        cmd += options
        cmd += [compiler["output_flag"], obj_file]
        checksum = md5(code.encode()).hexdigest()
        cachekey = (tuple(cmd), checksum)
        #TODO: include header checksums as well
        obj_data = cache.get(cachekey)
        if obj_data is None:
            currdir = os.getcwd()
            try:
                os.chdir(tempfile.gettempdir())
                with open(code_file, "w") as f:
                    f.write(code)
                cmd2 = " ".join(cmd)
                if compiler_verbose:
                    print(cmd2)
                process = subprocess.run(cmd2,shell=True, capture_output=True)
                print(process.stderr.decode())
                assert process.returncode == 0
                with open(obj_file, "rb") as f:
                    obj = f.read()
                obj_array = np.frombuffer(obj, dtype=np.uint8)
                cache[cachekey] = obj_array
            finally:
                try:
                    ###os.unlink(code_file)
                    os.unlink(obj_file)
                except:
                    pass
                os.chdir(currdir)
        binary_moduletree["objects"][objectname] = (obj_array, checksum)
    return binary_moduletree
