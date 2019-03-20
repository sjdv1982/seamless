import os
os.environ["SEAMLESS_COMMUNION_ID"] = "jobslave"
os.environ["SEAMLESS_COMMUNION_OUTGOING"] = "8602"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:8600"
import seamless
import asyncio
import sys
from seamless import communionserver

communionserver.configure_servant(
    transformer_job=True,
    transformer_result=True,
    transformer_result_level2=True
)
redis_sink = seamless.RedisSink()
redis_cache = seamless.RedisCache()

from seamless.core import context
ctx = context(toplevel=True)

loop = asyncio.get_event_loop()
if len(sys.argv) > 1:    
    run_time = float(sys.argv[1])
    loop.call_later(run_time, sys.exit)
loop.run_forever()