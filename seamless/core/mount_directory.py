"""Mounts raw deep-dict cells to/from directories
The contents are stored as <full file path>: <file content checksum> items.
"""


"""
Todo: function that takes mixed deep-dict cell, and fills it up
with directory contents, without mounting.
Likewise, function to write mixed deep-dict cell to directory.

For mounting, do something smarter.
Write:
Keep track of old deep-dict (is small, because checksums)
For a new deep-dict: create a differential, to write as little to disk as needed.
For old deep-dict, create reverse dict, i.e. buffer-to-filename
If buffer already exists under another filename, do hardlink.
Finally, remove no longer existing files and also have-become-empty subdirs (be like Git, no storage of empty dirs)
Read: in old deep-dict, store modification times as well. Don't reread if mtime isn't newer
"""

import os
from typing import Type

def _validate_cell(cell):
    from .cell import Cell
    if not isinstance(cell, Cell):
        raise TypeError(cell)
    if cell.celltype != "mixed":
        raise TypeError(f"celltype of {cell} must be mixed, not {cell.celltype}")
    if cell._hash_pattern != {"*": "##"}:
        raise TypeError(f"{cell} must be a deep dict with raw checksums")

def read_from_directory(directory, cell, reference_dir=None):
    """Takes mixed deep-dict cell, and fills it up with directory contents, without mounting.

Each keys is a file path.
If reference_dir is defined, all file paths are stored relative to this reference.
This function is not in any way optimized, e.g for parallel read/buffer calculation

The deep dict + its checksum are simply returned as a tuple.

Cell can be None.

If cell is not None, all file buffers are cached by Seamless.
Caching through a connected Seamless database will create a copy of all files 
 that are new to the database.
If there is no connected Seamless database, Seamless will hold all file buffers in-memory."""
    from .protocol.calculate_checksum import calculate_checksum_sync
    from .protocol.serialize import serialize_sync
    from .cache.buffer_cache import buffer_cache
    if not os.path.exists(directory) or not os.path.isdir(directory):
        raise OSError(directory)
    if cell is not None:
        _validate_cell(cell)
    result = {}
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            full_filename = os.path.join(dirpath, filename)
            key = full_filename
            if reference_dir is not None:
                key = os.path.relpath(full_filename, reference_dir)
            print(key)
            with open(full_filename, "rb") as f:
                buf = f.read()
            checksum = calculate_checksum_sync(buf)
            if checksum is None:   # shouldn't happen...
                continue
            if cell is not None:
                #buffer_cache.cache_buffer(checksum, buf)  
                # # No. If the user really wants to read a huge directory, it should be offloaded
                # #  to a Seamless database, if one is configured. cache_buffer doesn't do that.
                # # Use incref + decref instead. 
                # # This will trigger cache_buffer anyway, if there is no DB
                buffer_cache.incref_buffer(checksum, buf, True)
                buffer_cache.decref(checksum)
            result[key] = checksum.hex()
    result_buf = serialize_sync(result, "plain")
    result_checksum = calculate_checksum_sync(result_buf)
    assert result_checksum is not None
    buffer_cache.cache_buffer(result_checksum, result_buf)
    buffer_cache.guarantee_buffer_info(result_checksum, "plain")
    result_checksum = result_checksum.hex()
    if cell is not None:
        cell.set_checksum(result_checksum)
    return result, result_checksum

'''
def func():
    """
    From mount.py, return mtime.
    Note that directory mtime only updates when a file is created or deleted,
     not when content changes! Mounting big dirs is expensive!!
    """
            raise Exception  # invoke mount directory instead.
            if not os.path.exists(self.path) or not os.path.isdir(self.path):
                return None
            stat = os.stat(self.path)
            mtime = stat.st_mtime
            try:
                def scan_(path):
                    nonlocal mtime
                    with os.scandir(path) as it:
                        for entry in it:
                            if entry.is_file() or entry.is_dir():
                                f_mtime = entry.stat().st_mtime
                                #print(entry.path, f_mtime)
                                if mtime is None or f_mtime > mtime:
                                    mtime = f_mtime
                            if entry.is_dir():
                                scan_(entry.path)
                scan_(self.path)
            except RuntimeError:
                pass
            return mtime
'''
from .protocol.calculate_checksum import calculate_checksum, calculate_checksum_sync