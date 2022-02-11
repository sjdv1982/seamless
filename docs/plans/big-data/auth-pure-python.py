import cProfile, pstats, io
cProfile.profiler = cProfile.Profile()
cProfile.profiler.enable()

from seamless import calculate_checksum
from seamless.core.protocol.serialize import _serialize

repeat = int(10e6)
#repeat = int(5)
#for n in range(1000): # 2x10 GB
#for n in range(100): # 2x1 GB
for n in range(100):
    a = "A:%d:" % n + str(n%10) * repeat
    b = "B:%d:" % n + str(n%10) * repeat
    calculate_checksum(_serialize(a, "str"))
    calculate_checksum(_serialize(b, "str"))
    print(n+1)


import sys
sortby = 'tottime'
ps = pstats.Stats(cProfile.profiler, stream=sys.stdout).sort_stats(sortby)
ps.print_stats(10)
