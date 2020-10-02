import seamless
seamless.database_sink.connect()

# TODO: proper command line options (also for mounts)
import sys
from seamless.highlevel import Context
zipfile = sys.argv[1]
ctx = Context()
ctx.add_zip(zipfile)
