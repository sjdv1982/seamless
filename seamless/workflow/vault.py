"""Functions for loading and saving buffers from vaults"""

import os
import pathlib
import sys
import time

from seamless import Checksum, Buffer
from seamless.checksum.buffer_cache import (
    buffer_cache,
    empty_dict_checksum,
    empty_list_checksum,
)

SMALL_BIG_THRESHOLD = 100000  # for now, the same as buffer_cache.SMALL_BUFFER_LIMIT


class VaultLock:
    def __init__(self, dirname):
        self.dirname = dirname
        self.lockfile = pathlib.Path(dirname).joinpath(".LOCK")
        self.mtime = None

    def __enter__(self):
        while self.lockfile.exists():
            t = time.time()
            mtime = self.lockfile.stat().st_mtime
            if mtime > t + 120:
                print(f"Breaking vault lock on '{self.dirname}'", file=sys.stderr)
                break
            time.sleep(1)
        self.lockfile.touch()
        return self

    def __exit__(
        self, type, value, traceback
    ):  # pylint: disable=redefined-builtin, unused-variable
        self.lockfile.unlink()

    def touch(self):
        t = time.time()
        if self.mtime is None:
            self.mtime = t
        if t - self.mtime > 60:
            self.lockfile.touch()
            self.mtime = t


def save_vault_flat(dirname, annotated_checksums, buffer_dict):
    """Save vault in flat format (as a buffer dir)"""
    if not os.path.exists(dirname):
        os.makedirs(dirname, exist_ok=True)
    with VaultLock(dirname) as vl:
        for checksum, _is_dependent in annotated_checksums:
            buffer = buffer_dict[checksum]
            filename = os.path.join(dirname, str(checksum))
            with open(filename, "wb") as f:
                f.write(buffer)
                vl.touch()


def save_vault(dirname, annotated_checksums, buffer_dict):
    is_flat = False
    if os.path.exists(dirname):
        for dep in ("independent", "dependent"):
            dirn = os.path.join(dirname, dep)
            if os.path.exists(dirn):
                break
            for _, _, files in os.walk(dirname):
                for filename in files:
                    if filename.startswith("."):
                        continue
                    try:
                        Checksum(filename)
                        is_flat = True
                    except (TypeError, ValueError, AssertionError):
                        pass
                    break
    else:
        os.makedirs(dirname, exist_ok=True)
    if is_flat:
        return save_vault_flat(dirname, annotated_checksums, buffer_dict)

    dirs = {}
    for dep in ("independent", "dependent"):
        for size in ("small", "big"):
            dirn = os.path.join(dirname, dep, size)
            os.makedirs(dirn, exist_ok=True)
            with open(os.path.join(dirn, ".gitkeep"), "w") as f:
                pass
            dirs[dep, size] = dirn

    with VaultLock(dirname) as vl:
        for checksum, is_dependent in annotated_checksums:
            if checksum not in buffer_dict:
                print(
                    f"Skipping unknown buffer with checksum '{checksum}'",
                    file=sys.stderr,
                )
                continue
            buffer = buffer_dict[checksum]
            size = "small" if len(buffer) <= SMALL_BIG_THRESHOLD else "big"
            dep = "dependent" if is_dependent else "independent"
            dirn = dirs[dep, size]
            filename = os.path.join(dirn, str(checksum))
            with open(filename, "wb") as f:
                f.write(buffer)
                vl.touch()


def load_vault_flat(dirname, incref: bool) -> list[Checksum]:
    result = []
    for _, _, files in os.walk(dirname):
        for filename in files:
            filename = str(filename)
            if filename.startswith("."):
                continue
            checksum = Checksum(filename)
            if checksum in (empty_dict_checksum, empty_list_checksum):
                continue
            filename2 = os.path.join(dirname, filename)
            with open(filename2, "rb") as f:
                buffer = f.read()
            checksum2 = Buffer(buffer).get_checksum()
            if checksum2 != checksum:
                raise ValueError(
                    "Incorrect checksum for vault file '{}'".format(filename2)
                )
            buffer_cache.cache_buffer(checksum, buffer)
            if incref:
                buffer_cache.incref(checksum, persistent=False)
            result.append(checksum)
    return result


def load_vault(dirname, incref=False):
    if not os.path.exists(dirname):
        raise ValueError(dirname)
    result = []
    ok = False
    for dep in ("independent", "dependent"):
        for size in ("small", "big"):
            dirn = os.path.join(dirname, dep, size)
            if not os.path.exists(dirn):
                continue
            ok = True
            result += load_vault_flat(dirn, incref)
    if not ok:
        result += load_vault_flat(dirname, incref)
        if result:
            ok = True
    if not ok:
        raise ValueError("{} does not seem to be a Seamless vault".format(dirname))
    return result
