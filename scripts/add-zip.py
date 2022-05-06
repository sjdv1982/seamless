import seamless
from seamless.core.cache.buffer_cache import buffer_cache
import os

seamless.database_sink.connect()

# TODO: proper command line options (also for mounts)
import sys
from seamless.highlevel import Context
zipfile = sys.argv[1]
ctx = Context()
checksums = ctx.add_zip(zipfile, incref=True)
for checksum in checksums:
    buffer_cache.decref(bytes.fromhex(checksum))
