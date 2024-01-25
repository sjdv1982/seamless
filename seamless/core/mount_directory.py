"""Reads and writes raw deep-dict cells to/from directories
The contents are stored as <full file path>: <file content checksum> items.
"""

import logging
import os
import shutil

from seamless.core.protocol.deserialize import deserialize_sync

def _validate_cell(cell):
    from .cell import Cell
    if not isinstance(cell, Cell):
        raise TypeError(cell)
    if cell.celltype != "mixed":
        raise TypeError(f"celltype of {cell} must be mixed, not {cell.celltype}")
    if cell._hash_pattern != {"*": "##"}:
        raise TypeError(f"{cell} must be a deep dict with raw checksums")

def read_from_directory(directory, cell, reference_dir=None, *, text_only):
    """Takes mixed cell, and fills it up with directory contents, without mounting.

Each key is a file path.
If reference_dir is defined, all file paths are stored relative to this reference.
This function is not in any way optimized, e.g for parallel read/buffer calculation

The dict + its checksum are simply returned as a tuple.

Cell can be None.
"""
    from .protocol.calculate_checksum import calculate_checksum_sync
    from .protocol.serialize import serialize_sync
    from .cache.buffer_cache import buffer_cache
    if not os.path.exists(directory) or not os.path.isdir(directory):
        raise OSError(directory)
    if cell is not None:
        _validate_cell(cell)
    result = {}
    if reference_dir is None:
        reference_dir = directory
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            full_filename = os.path.join(dirpath, filename)
            key = os.path.relpath(full_filename, reference_dir)
            with open(full_filename, "rb") as f:
                buf = f.read()
            if text_only:
                try:
                    result[key] = deserialize_sync(buf, None, "text", copy=False)
                except (ValueError, UnicodeDecodeError):
                    continue
            else:
                result[key] = deserialize_raw(buf)
    result_buf = serialize_sync(result, "mixed")
    result_checksum = calculate_checksum_sync(result_buf)
    assert result_checksum is not None
    buffer_cache.cache_buffer(result_checksum, result_buf)
    buffer_cache.guarantee_buffer_info(result_checksum, "plain", sync_to_remote=False)
    result_checksum = result_checksum.hex()
    if cell is not None:
        cell.set_checksum(result_checksum)
    return result, result_checksum

def deep_read_from_directory(directory, cell, reference_dir=None, 
    *, text_only, cache_buffers=False
):
    """Takes mixed deep-dict cell, and fills it up with directory contents, without mounting.

Each key is a file path.
If reference_dir is defined, all file paths are stored relative to this reference.
This function is not in any way optimized, e.g for parallel read/buffer calculation

The deep dict + its checksum are simply returned as a tuple.

Cell can be None.

If cell is not None or cache_buffers, all file buffers are cached by Seamless.
Caching through a connected Seamless database will create a copy of all files 
 that are new to the database.
If there is no connected Seamless buffer storage, Seamless will hold all file buffers in-memory."""
    from .protocol.calculate_checksum import calculate_checksum_sync
    from .protocol.serialize import serialize_sync
    from .cache.buffer_cache import buffer_cache
    if not os.path.exists(directory) or not os.path.isdir(directory):
        raise OSError(directory)
    if cell is not None:
        _validate_cell(cell)
    result = {}
    if reference_dir is None:
        reference_dir = directory
    for dirpath, _, filenames in os.walk(directory):
        for filename in filenames:
            full_filename = os.path.join(dirpath, filename)
            key = os.path.relpath(full_filename, reference_dir)
            with open(full_filename, "rb") as f:
                buf = f.read()
            if text_only:
                try:
                    txt = deserialize_sync(buf, None, "text", copy=False)
                    buf = serialize_sync(txt, "text")
                except (ValueError, UnicodeDecodeError):
                    continue
            checksum = calculate_checksum_sync(buf)
            if checksum is None:   # shouldn't happen...
                continue
            if cell is not None or cache_buffers:
                #buffer_cache.cache_buffer(checksum, buf)  
                # # No. If the user really wants to read a huge directory, it should be offloaded
                # #  to Seamless buffer storage, ifconfigured. cache_buffer doesn't do that.
                # # Use incref + decref instead. 
                # # This will trigger cache_buffer anyway, if there is no buffer storage
                buffer_cache.incref_buffer(checksum, buf, persistent=True)
                buffer_cache.decref(checksum)
            result[key] = checksum.hex()
    result_buf = serialize_sync(result, "plain")
    result_checksum = calculate_checksum_sync(result_buf)
    assert result_checksum is not None
    if cell is not None or cache_buffers:
        buffer_cache.cache_buffer(result_checksum, result_buf)
        buffer_cache.guarantee_buffer_info(result_checksum, "plain", sync_to_remote=False)
    result_checksum = result_checksum.hex()
    if cell is not None:
        cell.set_checksum(result_checksum)
    return result, result_checksum

def write_to_directory(directory, data, *, cleanup, deep, text_only):
    """Writes data to directory
    
    Data must be a (deep) folder"""
    abs_dir = os.path.abspath(directory)
    os.makedirs(abs_dir, exist_ok=True)
    all_files = set()
    all_dirs = set()
    if isinstance(data, dict):
        for k,v in data.items():
            kdir, _ = os.path.split(k)
            if kdir:            
                kdir2 = os.path.join(abs_dir, kdir)
                if kdir2 not in all_dirs:
                    all_dirs.add(kdir2)
                    os.makedirs(kdir2, exist_ok=True)
            filename = os.path.join(abs_dir, k)
            all_files.add(filename)
            if deep:
                cs = parse_checksum(v)
                buf = get_buffer(cs, remote=True, deep=False)
                if buf is None:
                    logging.warn("CacheMissError: {}".format(v))
                    continue                
            else:
                buf = serialize_raw(v)
            if text_only:
                try:
                    txt = deserialize_sync(buf, None, "text", copy=False)
                except (ValueError, UnicodeDecodeError):
                    continue
                with open(filename, "w") as f:
                    f.write(txt)
            else:
                with open(filename, "wb") as f:
                    f.write(buf)
    if cleanup:
        with os.scandir(directory) as it:
            for entry in it:
                path = os.path.abspath(entry.path)
                if entry.is_file():
                    if path not in all_files:
                        os.unlink(path)
                elif entry.is_dir():
                    if path not in all_dirs:
                        shutil.rmtree(path, ignore_errors=True)

def get_directory_mtime(path):
    """return mtime.
    Note that directory mtime only updates when a file is created or deleted,
        not when content changes! Mounting big dirs is expensive!!
    """
    if not os.path.exists(path) or not os.path.isdir(path):
        return None
    stat = os.stat(path)
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
        scan_(path)
    except RuntimeError:
        pass
    return mtime

from .protocol.calculate_checksum import calculate_checksum, calculate_checksum_sync
from ..util import parse_checksum
from .protocol.deep_structure import deserialize_raw, serialize_raw
from .protocol.get_buffer import get_buffer