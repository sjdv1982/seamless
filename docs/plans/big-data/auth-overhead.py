"""
Another performance test that just does auth testing
"""

import seamless
import time

seamless.set_ncores(8) ###
seamless.set_parallel_evaluations(10000)  ###

import logging
#logging.basicConfig()
###logging.getLogger("seamless").setLevel(logging.DEBUG)




from datetime import timedelta
class ElapsedFormatter():

    def __init__(self):
        self.start_time = time.time()

    def format(self, record):
        elapsed_seconds = record.created - self.start_time
        #using timedelta here for convenient default formatting
        elapsed = timedelta(seconds = elapsed_seconds)
        return "{} {}".format(elapsed, record.getMessage())

#add custom formatter to root logger for simple demonstration
handler = logging.StreamHandler()
handler.setFormatter(ElapsedFormatter())
logging.getLogger().addHandler(handler)


from seamless.highlevel import Context, Cell


ctx = Context()
ctx.data_a = Cell()
ctx.data_b = Cell()
ctx.compute()
ctx.data_a.hash_pattern = {"!": "#"}
ctx.data_b.hash_pattern = {"!": "#"}
ctx.data_a2 = Cell("str")
ctx.data_b2 = Cell("str")
ctx.compute()

import cProfile, pstats, io
cProfile.profiler = cProfile.Profile()
cProfile.profiler.enable()

for n in range(100):
    name = "pdata_a" + str(n+1)
    setattr(ctx, name, Cell("str"))
    name = "pdata_b" + str(n+1)
    setattr(ctx, name, Cell("str"))
ctx.compute()

repeat = int(10e6)
#repeat = int(5)
#for n in range(1000): # 2x10 GB
#for n in range(100): # 2x1 GB
for n in range(100):
    a = "A:%d:" % n + str(n%10) * repeat
    b = "B:%d:" % n + str(n%10) * repeat
    ctx.data_a[n] = a
    ctx.data_b[n] = b
    #ctx.data_a2.set(a)
    #ctx.data_b2.set(b)

    """
    name = "pdata_a" + str(n+1)
    getattr(ctx, name).set(a)
    name = "pdata_b" + str(n+1)
    getattr(ctx, name).set(b)
    """

    if n % 20 == 0:
        ctx.compute()
    print(n+1)

ctx.compute()
print(ctx.data_a.checksum)
print(ctx.data_b.checksum)

import io, pstats
import sys
sortby = 'tottime'
ps = pstats.Stats(cProfile.profiler, stream=sys.stdout).sort_stats(sortby)
ps.print_stats(40)
