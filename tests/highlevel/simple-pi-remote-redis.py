#use with jobslave.py

import os
os.environ["SEAMLESS_COMMUNION_ID"] = "simple-pi-remote"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:8602"

import seamless
seamless.set_ncores(0)
from seamless import communionserver

redis_sink = seamless.RedisSink()
redis_cache = seamless.RedisCache()

communionserver.configure_master(
    transformer_job=True,
)

import math
from seamless.highlevel import Context, Cell
import json
ctx = Context()
ctx.pi = math.pi
ctx.doubleit = lambda a: 2 * a
ctx.doubleit.a = ctx.pi
ctx.twopi = ctx.doubleit
ctx.translate()

ctx.equilibrate()
print(ctx.pi.value)
print(ctx.twopi.value)

ctx.doubleit.code = lambda a: 42
ctx.equilibrate()
print(ctx.pi.value)
print(ctx.twopi.value)

ctx.translate(force=True)
ctx.equilibrate()
print(ctx.pi.value)
print(ctx.twopi.value)
print()

ctx.doubleit.code = lambda a: 2 * a
ctx.equilibrate()
print(ctx.pi.value)
print(ctx.twopi.value)
