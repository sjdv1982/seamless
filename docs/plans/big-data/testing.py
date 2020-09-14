"""
Performance tests based on tests/highlevel/high-in-low6-memory.py

Note that transformations run in subprocesses, so this is all about latency, not total CPU usage
"""

import seamless

import seamless.core.execute
seamless.core.execute.DIRECT_PRINT = True

seamless.database_sink.connect()
seamless.database_cache.connect()
#seamless.set_ncores(2)
#seamless.set_parallel_evaluations(5)

seamless.set_ncores(8) ###
seamless.set_parallel_evaluations(10)  ###

"""
import logging
logging.basicConfig()
logging.getLogger("seamless").setLevel(logging.DEBUG)
"""

from seamless.highlevel import Context, Cell, Macro
from seamless.highlevel.library import LibraryContainer

import cProfile, pstats, io
cProfile.profiler = cProfile.Profile()

mylib = LibraryContainer("mylib")
mylib.map_list_N = Context()
def constructor(ctx, libctx, context_graph, inp, result):
    m = ctx.m = Macro()
    m.graph = context_graph
    m.pins.result = {"io": "output", "celltype": "mixed", "hash_pattern": {"!": "#"}}

    ctx.inp = Context()
    ctx.cs_inp = Context()
    inp_prefix = "INPUT_"
    m.inp_prefix = inp_prefix
    for key in inp:
        c = Cell()
        ctx.inp[key] = c
        c.hash_pattern = {"!": "#"}
        inp[key].connect(c)
        ctx.cs_inp[key] = Cell("checksum")
        ctx.cs_inp[key] = ctx.inp[key]
        setattr(m, inp_prefix + key , ctx.cs_inp[key])

    def map_list_N(ctx, inp_prefix, graph, **inp):
        #print("INP", inp)
        first_k = list(inp.keys())[0]
        length = len(inp[first_k])
        first_k = first_k[len(inp_prefix):]
        for k0 in inp:
            k = k0[len(inp_prefix):]
            if len(inp[k0]) != length:
                err = "all cells in inp must have the same length, but '{}' has length {} while '{}' has length {}"
                raise ValueError(err.format(k, len(inp[k0]), first_k, length))

        print("LENGTH", length)

        from seamless.core import Cell as CoreCell
        from seamless.core.unbound_context import UnboundContext
        pseudo_connections = []
        ctx.result = cell("mixed", hash_pattern = {"!": "#"})

        ctx.sc_data = cell("mixed", hash_pattern = {"!": "#"})
        ctx.sc_buffer = cell("mixed", hash_pattern = {"!": "#"})
        ctx.sc = StructuredCell(
            data=ctx.sc_data,
            buffer=ctx.sc_buffer,
            inchannels=[(n,) for n in range(length)],
            outchannels=[()],
            hash_pattern = {"!": "#"}
        )

        for n in range(length):
            #print("MACRO", n+1)
            hc = HighLevelContext(graph)

            subctx = "subctx%d" % (n+1)
            setattr(ctx, subctx, hc)

            if not hasattr(hc, "inp"):
                raise TypeError("map_list_N context must have a subcontext called 'inp'")
            hci = hc.inp
            if not isinstance(hci, UnboundContext):
                raise TypeError("map_list_N context must have an attribute 'inp' that is a context, not a {}".format(type(hci)))

            for k0 in inp:
                k = k0[len(inp_prefix):]
                if not hasattr(hci, k):
                    raise TypeError("map_list_N context must have a cell called inp.'{}'".format(k))
                if isinstance(hci[k], StructuredCell):
                    raise TypeError("map_list_N context has a cell called inp.'{}', but its celltype must be mixed, not structured".format(k))
                if not isinstance(hci[k], CoreCell):
                    raise TypeError("map_list_N context must have an attribute inp.'{}' that is a cell, not a {}".format(k, type(hci[k])))
                if hci[k].celltype != "mixed":
                    raise TypeError("map_list_N context has a cell called inp.'{}', but its celltype must be mixed, not {}".format(k, hci[k].celltype))

                con = [".." + k], ["ctx", subctx, "inp", k]
                pseudo_connections.append(con)
                cs = inp[k0][n]
                hci[k].set_checksum(cs)

            resultname = "result%d" % (n+1)
            setattr(ctx, resultname, cell("mixed"))
            c = getattr(ctx, resultname)
            hc.result.connect(c)
            c.connect(ctx.sc.inchannels[(n,)])
            con = ["ctx", subctx, "result"], ["..result"]
            pseudo_connections.append(con)

        ctx.sc.outchannels[()].connect(ctx.result)
        ctx._pseudo_connections = pseudo_connections
        print("/MACRO")

        """
        import logging
        logging.basicConfig()
        logging.getLogger("seamless").setLevel(logging.DEBUG)
        """

        import cProfile
        cProfile.profiler.enable()

    m.code = map_list_N
    ctx.result = Cell()
    ctx.result.hash_pattern = {"!": "#"}
    ctx.result = m.result
    result.connect_from(ctx.result)


mylib.map_list_N.constructor = constructor
mylib.map_list_N.params = {
    "context_graph": "context",
    "inp": {
        "type": "celldict",
        "io": "input"
    },
    "result": {
        "type": "cell",
        "io": "output"
    },
}

ctx = Context()
ctx.adder = Context()
sctx = ctx.adder
sctx.inp = Context()
sctx.inp.a = Cell("mixed")
sctx.inp.b = Cell("mixed")
sctx.a = Cell("str")
sctx.b = Cell("str")
sctx.a = sctx.inp.a
sctx.b = sctx.inp.b
def add(a,b):
    print("ADD", a[:10])
    return a+b
sctx.add = add
sctx.add.a = sctx.a
sctx.add.b = sctx.b
sctx.result = sctx.add
sctx.result.celltype = "mixed"
ctx.compute()

ctx.data_a = Cell()
ctx.data_a.hash_pattern = {"!": "#"}
ctx.data_b = Cell()
ctx.data_b.hash_pattern = {"!": "#"}
ctx.compute()

# Next section is 14.5 secs (if the database is filled), but can be elided to ~0.5s by setting checksum directly (if in flatfile cache).
# Not having a DB at all is also 13.5 secs, so DB request communication (without upload) doesn't cost much.

repeat = int(10e6)
#repeat = int(5) ###
#for n in range(1000): # 2x10 GB
#for n in range(100): # 2x1 GB
for n in range(100):
    a = "A:%d:" % n + str(n%10) * repeat
    b = "B:%d:" % n + str(n%10) * repeat
    ctx.data_a[n] = a
    ctx.data_b[n] = b
    if n % 20 == 0:
        ctx.compute()
    print(n+1)

ctx.compute()
print(ctx.data_a.checksum)
print(ctx.data_b.checksum)

"""
ctx.data_a.set_checksum("983730afb7ab41d524b72f1097daaf4a3c15b98943291f96e523730849cabe8c")
ctx.data_b.set_checksum("46dabc02b59be44064a9e06dd50bc6841833578c2b6339fbc43f090cc17831fa")
"""

#
### For repeat=10 million
### ctx.data_a.set_checksum("983730afb7ab41d524b72f1097daaf4a3c15b98943291f96e523730849cabe8c")
### ctx.data_b.set_checksum("46dabc02b59be44064a9e06dd50bc6841833578c2b6339fbc43f090cc17831fa")

### For repeat=5
### ctx.data_a.set_checksum("9b4a551a6c1c5830d6070b9c22ae1788b9743e9637be47d56103bcda019a897c")
### ctx.data_b.set_checksum("9820f1ab795db7b0d195f21966ecb071d76e9ce2fd3a90845974a3905584eb3e")
ctx.compute()
#

# If the database has been filled:

# - 1.5 secs up to here (with the above elision). Another 1.5 secs to execute the length-100 macro
# - it is about 9 seconds to propagate the signals (evidenced from re-translation, minus macro execution)
# - Since total time is about 30 secs, that leaves about 21 - 3 = 18 secs for database buffer download and expression evaluation
# - Signal propagation still scales very much with buffer size, as for repeat 5:
#       - retranslation is 3.7 (5.2 - 1.5) seconds, rather than 9
#       - total time is 6.4 seconds (9.4 - 3), rather than 30.
#       Why is this so?? Expressions should be of the same size, since everything is a deep structure ??


# If the database has NOT been filled:
# - Filling up the input alone is 25.5 seconds (so 11 seconds for the raw upload, since it is 14.5 seconds w/o elision)
# - 119 secs in total; that leaves about 94 - 3 = 91 sec for database buffer download, expression evaluation, transformation and upload
# - again, about 10 secs for retranslation. Retranslation is only 8 - 1.5 = 6.5 secs w/o database.
# - Not having a DB at all is 83 secs in total, leaving 83 - 13.5 - 6.5 - 3 = 60 secs for expression evaluation and transformation
#   This is still a rather hefty overhead from the checksumming + cell division:
#       - Direct calculation in Python is ~1.75 seconds. Deepcopies don't change anything (very efficient for str)
#       - Direct calculation + calculating checksums for inputs and outputs makes it 14 seconds
#       - The hash is calculated only once

ctx.result = Cell()
ctx.result.hash_pattern = {"!": "#"}
ctx.compute()

ctx.include(mylib.map_list_N)
ctx.inst = ctx.lib.map_list_N(
    context_graph = ctx.adder,
    inp = {"a": ctx.data_a, "b": ctx.data_b},
    result = ctx.result
)
ctx.compute()

print("Exception:", ctx.inst.ctx.m.exception)
print(ctx.result.data)

import io, pstats
s = io.StringIO()
sortby = 'tottime'
ps = pstats.Stats(cProfile.profiler, stream=s).sort_stats(sortby)
ps.print_stats(40)
###print(s.getvalue())
import time; t0 = time.time()

"""
print("Re-set")
graph = ctx.get_graph()
ctx_dummy = Context()
dummy_graph = ctx_dummy.get_graph()
ctx.set_graph(dummy_graph)
ctx.translate(force=True)
ctx.compute()
print(time.time()-t0)
print("Re-eval")
ctx.set_graph(graph)
"""

ctx.translate(force=True)
ctx.compute()
print(time.time()-t0)
