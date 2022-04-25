from seamless.pylru import lrucache
from seamless.util import parse_checksum
import os
import glob
import collections
import json
import atexit
import time
import asyncio
import sys

# A bucket will have up to 64 byte keys, and values of a few hundred bytes.
# In total, maybe a kilobyte per entry
MAX_BUCKET_SIZE = 1000  # split a bucket if it contains more than BUCKET_MAX_SIZE
CACHE_SIZE = 1000   # keep CACHE_SIZE buckets in memory
# With this, total memory consumption should be 1-2 GB max.

LAST_CACHE_WRITTEN = None  # last time a buffer cache was evicted and written to disk

def write_bucket(filename, value):
    global LAST_CACHE_WRITTEN
    with open(filename, "w") as f:
        json.dump(value, f, sort_keys=True, indent=2)
        LAST_CACHE_WRITTEN = time.time()

bucket_cache = lrucache(CACHE_SIZE, write_bucket)
    
def write_all():
    for filename, value in bucket_cache.items():
        write_bucket(filename, value)
    bucket_cache.clear()

atexit.register(write_all)

async def decay_cache(min_wait):
    while 1:
        while not len(bucket_cache):
            await asyncio.sleep(1)
        if LAST_CACHE_WRITTEN is None:
            await asyncio.sleep(min_wait)
        if not len(bucket_cache):
            continue
        if LAST_CACHE_WRITTEN is not None:
            while time.time() - LAST_CACHE_WRITTEN < min_wait:
                await asyncio.sleep(1)
        if not len(bucket_cache):
            continue
        oldest = list(bucket_cache.keys())[-1]
        value = bucket_cache[oldest]
        write_bucket(oldest, value)
        bucket_cache.pop(oldest)  # does not call write_bucket

asyncio.ensure_future(decay_cache(10))

def split_bucket(bucket:dict):
    """Finds the most common first letter of the key.
Entries starting with this key are split off from bucket and added to new_bucket.
Returns most_common_first, new_bucket
"""
    all_firsts = [k[0] for k in bucket.keys()]
    most_common_first = collections.Counter(all_firsts).most_common()[0][0]
    new_bucket = {}
    for k in list(bucket.keys()):
        if k[0] == most_common_first:
            v = bucket.pop(k)
            new_bucket[k[1:]] = v
    return most_common_first, new_bucket

def is_hex(c):
    try:
        bytes.fromhex(c+"0")
        return True
    except ValueError:
        return False

def get_data(filename):
    result = bucket_cache.get(filename)
    if result is None:
        try:
            with open(filename, "r") as f:
                try:
                    result = json.load(f)
                    if result is None:
                        result = {}
                except Exception:
                    print("READING ERROR", filename, file=sys.stderr)
                    result = {}
        except FileNotFoundError:
            result = {}
        bucket_cache[filename] = result
    return result

class TopBucket:
    def __init__(self, directory, max_size=MAX_BUCKET_SIZE):
        self.directory = directory
        self.max_size = max_size
        self._file = os.path.join(self.directory, "ALL")
        self.children = {}
        self._read_children()
        self._dir_exist_validated = False

    def _read_children(self):
        if not os.path.exists(self.directory):
            return
        files = glob.glob(os.path.join(self.directory, "?"))
        for f in files:
            first = f[-1]
            if not is_hex(first):
                continue
            self.children[first] = Bucket(
                self.directory, first, self.max_size
            )

    def set(self, checksum, value):
        try:
            checksum = parse_checksum(checksum)
        except ValueError:
            raise ValueError(checksum) from None
        json.dumps(value)
        if not self._dir_exist_validated:
            if not os.path.exists(self.directory):
                os.mkdir(self.directory)
            self._dir_exist_validated = True
        first = checksum[0]
        try:
            child = self.children[first]
        except KeyError:
            filename = os.path.join(self.directory, self._file)
            data = get_data(filename)
            if value is None:
                old = data.pop(checksum, None)
                deleted = (old is not None)
                return deleted
            else:
                data[checksum] = value
                while len(data) > self.max_size:
                    first, child_bucket = split_bucket(data)
                    child = Bucket(
                        self.directory, first, self.max_size,
                        data=child_bucket
                    )
                    self.children[first] = child
                    while len(child_bucket) > self.max_size:
                        child._split(child_bucket)
        else:
            child.set(checksum[1:], value)

    def get(self, checksum):
        if not self._dir_exist_validated:
            if not os.path.exists(self.directory):
                os.mkdir(self.directory)
            self._dir_exist_validated = True
        checksum = parse_checksum(checksum)
        first = checksum[0]
        try:
            child = self.children[first]
        except KeyError:
            filename = os.path.join(self.directory, self._file)
            data = get_data(filename)
            return data.get(checksum)
        else:
            return child.get(checksum[1:])


class Bucket:
    def __init__(self, directory, head, max_size, *, data=None):
        #print("BUCKET", head)
        self.directory = directory
        self.head = head
        self.max_size = max_size
        self._file = os.path.join(self.directory, self.head)
        if data is not None:
            bucket_cache[self._file] = data
        self.children = {}
        self._read_children()

    def _read_children(self):
        files = glob.glob(self._file + "?")
        for f in files:
            first = f[-1]
            if not is_hex(first):
                continue
            new_head = self.head + first
            self.children[first] = Bucket(
                self.directory, new_head, self.max_size
            )

    def _split(self, data):
        first, child_bucket = split_bucket(data)
        new_head = self.head + first
        child = Bucket(
            self.directory, new_head, self.max_size,
            data=child_bucket
        )           
        self.children[first] = child
        while len(child_bucket) > self.max_size:
            child._split(child_bucket)

    def set(self, checksum, value):
        first = checksum[0]
        try:
            child = self.children[first]
        except KeyError:
            filename = os.path.join(self.directory, self._file)
            data = get_data(filename)
            if value is None:
                data.pop(checksum, None)
            else:
                data[checksum] = value
                if len(checksum) > 1:
                    while len(data) > self.max_size:
                        self._split(data)
    
        else:
            child.set(checksum[1:], value)

    def get(self, checksum):
        first = checksum[0]
        try:
            child = self.children[first]
        except KeyError:
            filename = os.path.join(self.directory, self._file)
            data = get_data(filename)
            return data.get(checksum)
        else:
            return child.get(checksum[1:])

if __name__ == "__main__":
    dir = "/tmp/database_bucket_test"    
    # Run this twice; 
    # the first time, "dir" should not exist, it will be created
    # the second time, it will be read
    create = not os.path.exists(dir)
    if create:        
        os.mkdir(dir)
    #max_size = MAX_BUCKET_SIZE 
    max_size = 3 # for testing
    b = TopBucket(directory=dir,max_size=max_size)
    keys = [
        "123abc1",
        "123abc2",
        "123abc3",
        "123abc4",
        "123abd1",
        "123abd2",
        "123abd3",
        "123abe1",
        "123abe2",
        "123abe3",
        "123abe4",
        "123af00",
        "123af01",
        "124dddd",
        "134eeee",
        "234ffff",
    ]
    if create:
        for knr, k in enumerate(keys):
            checksum = k + (64-len(k))* "0"
            value = knr+1
            b.set(checksum, value)
    for knr, k in enumerate(keys):
        checksum = k + (64-len(k))* "0"
        value = b.get(checksum)
        print(value)
