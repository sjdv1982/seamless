import seamless
redis_sink = seamless.RedisSink()

# TODO: proper command line options (also for mounts)
import sys
from seamless.highlevel import Context
zipfile = sys.argv[1]
ctx = Context()
ctx.add_zip(zipfile)
