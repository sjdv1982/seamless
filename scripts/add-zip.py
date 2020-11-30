import seamless
from seamless.core.cache.buffer_cache import buffer_cache
import os

env = os.environ
params = {}
db_host = env.get("SEAMLESS_DATABASE_HOST")
if db_host is not None:
    params["host"] = db_host
db_port = env.get("SEAMLESS_DATABASE_PORT")
if db_port is not None:
    params["port"] = db_port

seamless.database_sink.connect(**params)

# TODO: proper command line options (also for mounts)
import sys
from seamless.highlevel import Context
zipfile = sys.argv[1]
ctx = Context()
checksums = ctx.add_zip(zipfile, incref=True)
for checksum in checksums:
    buffer_cache.decref(bytes.fromhex(checksum))
