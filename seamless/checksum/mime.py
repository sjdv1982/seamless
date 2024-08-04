"""Functions related to MIME and file extensions.
This is mostly important for mounting and for the shareserver"""

import os

mimetypes_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mime.types")
mimetypes = {}
mimetypes_rev = {}

for l in open(mimetypes_file, "r"):
    pound = l.find("#")
    if pound > -1:
        l = l[:pound]
    l = l.lstrip()
    if not len(l):
        continue
    fields = l.split()
    mimetype, extensions = fields[0], fields[1:]
    mimetypes[mimetype] = []
    for extension in extensions:
        if extension in mimetypes_rev:
            ###warnings.warn("file extension .'%s' has multiple media (MIME) types" % extension)
            continue
        else:
            mimetypes_rev[extension] = mimetype
        mimetypes[mimetype].append(extension)


def language_to_extension(language: str, fallback=None):
    """Get programming language file extensions"""
    try:
        return language_to_ext[language]
    except KeyError:
        if fallback is None:
            raise KeyError(language) from None
        return fallback


language_to_ext = {
    "python": "py",
    "c": "c",
    "cuda": "cu",
    "cpp": "cpp",
    "fortran": "f",
    "javascript": "js",
    "bash": "bash",
}
celltype_to_ext = {
    "text": "txt",
    "str": "txt",
    "python": "py",
    "transformer": "py",
    "reactor": "py",
    "macro": "py",
    "plain": "json",
    "int": "json",
    "float": "json",
    "bool": "json",
    "cson": "cson",
    "yaml": "yaml",
    "binary": "npy",
    "bytes": None,
    "mixed": "mixed",
    None: None,
}


def get_mime(celltype) -> str | None:
    """Get the default MIME of a celltype"""
    ext = celltype_to_ext[celltype]
    if ext is None:
        return None
    mime = mimetypes_rev[ext]
    return mime


def language_to_mime(language) -> str:
    """Get the MIME type for a programming language"""
    ext = language_to_ext[language]
    mime = mimetypes_rev[ext]
    return mime


def ext_to_mime(ext) -> str:
    """Find the MIME type of a file extension"""
    return mimetypes_rev[ext]
