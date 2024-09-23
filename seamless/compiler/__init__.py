"""
Takes a JSON dict of source object definitions (source code strings, language
property, compiler options, etc.)
 and generates a dict-of-binary-objects (.o / .obj)
Linking options etc. are passed through.
"""

import os
from seamless.util import cson2json

from .compile import compile, complete  # pylint: disable=redefined-builtin

mydir = os.path.abspath(os.path.split(__file__)[0])
compilers_cson_file = os.path.join(mydir, "compilers.cson")
languages_cson_file = os.path.join(mydir, "languages.cson")
with open(compilers_cson_file) as f:
    compilers_cson = f.read()
compilers = cson2json(compilers_cson)
with open(languages_cson_file) as f:
    languages_cson = f.read()
languages = cson2json(languages_cson)


def find_language(lang, languages=None):  # pylint: disable=redefined-outer-name
    """Find a compiled language lang.
    Return a tuple lang, language_dict, file_extension"""
    langs = languages
    if langs is None:
        langs = globals()["languages"]
    lang2 = lang
    if lang == "docker":
        lang2 = "bash"
    try:
        language = langs[lang2]
        extension = language.get("extension")
        if isinstance(extension, list):
            extension = extension[0]
    except KeyError:
        for _, language in langs.items():
            ext = language.get("extension", [])
            if isinstance(ext, str):
                if ext == lang2:
                    break
            else:
                if lang2 in ext:
                    break
        else:
            raise KeyError("Unknown language: {}".format(lang2)) from None
        extension = lang2
    return lang, language, extension


__all__ = ["compilers", "languages", "find_language", "compile", "complete"]
