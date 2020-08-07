import os, time, warnings
import shutil
import asyncio
from contextlib import contextmanager

MAX_STALE_LOCK_TIME = 300 # after this time, assume that the FlatFileSink holding the lock was killed prematurely

class FlatFileBase:
    def __init__(self, directory, config):
        self.directory = directory
        self.config = config
        if not os.path.exists(directory):
            raise OSError("Flatfile directory '{}' does not exist".format(directory))
        d = self.directory
        lock_dir = d + os.sep + "locks"
        if not os.path.exists(lock_dir):
            os.mkdir(lock_dir)
        self.lock_dir = lock_dir

    @property
    def id(self):
        return self.directory

    def _filename(self, key):
        d = self.directory
        filename = d + os.sep + key
        return filename

    async def acquire_lock(self, key):
        d = self.directory
        lock_file = self.lock_dir + os.sep + key
        if not os.path.exists(lock_file):
            with open(lock_file, "w"):
                pass
            return lock_file
        mtime = os.stat(lock_file).st_mtime
        while 1:
            if time.time() - mtime > MAX_STALE_LOCK_TIME:
                warnings.warn("FlatFile lock {} went stale, trying to break it...".format(key))
                os.unlink(lock_file)
                return lock_file
            await asyncio.sleep(1)
            if not os.path.exists(lock_file):
                return None

    async def has_key(self, key):
        if isinstance(key, bytes):
            key = key.decode()
        filename = self._filename(key)
        return os.path.exists(filename)

    async def delete_key(self, key):
        if isinstance(key, bytes):
            key = key.decode()
        lock_file = await self.acquire_lock(key)
        try:
            filename = self._filename(key)
            os.unlink(filename)
        finally:
            if lock_file is not None:
                os.unlink(lock_file)

class FlatFileSink(FlatFileBase):

    async def set(self, key, value, authoritative=True, importance=None):
        if isinstance(key, bytes):
            key = key.decode()
        assert isinstance(value, bytes)
        lock_file = await self.acquire_lock(key)
        try:
            filename = self._filename(key)
            with open(filename, "bw") as f:
                f.write(value)
        finally:
            if lock_file is not None:
                os.unlink(lock_file)

    async def rename(self, key1, key2):
        """Renames a buffer, assumes that key2 is authoritative"""
        if isinstance(key1, bytes):
            key1 = key1.decode()
        if isinstance(key2, bytes):
            key2 = key2.decode()
        lock_file1 = await self.acquire_lock(key1)
        lock_file2 = await self.acquire_lock(key2)
        try:
            filename1 = self._filename(key1)
            filename2 = self._filename(key2)
            shutil.move(filename1, filename2)
        finally:
            if lock_file1 is not None:
                os.unlink(lock_file1)
            if lock_file2 is not None:
                os.unlink(lock_file2)

    async def add_sem2syn(self, key, syn_checksums):
        if isinstance(key, bytes):
            key = key.decode()
        lock_file = await self.acquire_lock(key)
        try:
            filename = self._filename(key)
            if os.path.exists(filename):
                with open(filename, "r") as f:
                    curr_syn_checksums = set(f.readlines())
            else:
                curr_syn_checksums = set()
            with open(filename, "at") as f:
                for syn_checksum in syn_checksums:
                    assert isinstance(syn_checksum, bytes)
                    if syn_checksum not in curr_syn_checksums:
                        print(syn_checksum.decode(), file=f)
                        curr_syn_checksums.add(syn_checksum)
        finally:
            if lock_file is not None:
                os.unlink(lock_file)


class FlatFileSource(FlatFileBase):

    async def get(self, key):
        if isinstance(key, bytes):
            key = key.decode()
        filename = self._filename(key)
        try:
            with open(filename, "br") as f:
                return f.read()
        except OSError:
            return None

    async def get_sem2syn(self, key):
        if isinstance(key, bytes):
            key = key.decode()
        filename = self._filename(key)
        if os.path.exists(filename):
            with open(filename, "rt") as f:
                syn_checksums = {line.strip("\n").encode() for line in f.readlines()}
        else:
            syn_checksums = set()
        return syn_checksums



def get_source(config):
    directory = config["directory"]
    directory = os.path.abspath(os.path.expanduser(directory))
    return FlatFileSource(directory, config)

def get_sink(config):
    directory = config["directory"]
    return FlatFileSink(directory, config)
