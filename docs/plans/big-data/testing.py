"""
Performance tests based on tests/highlevel/high-in-low6-memory.py
See also auth-*py.

- Data overhead is now at ~6.5 ms / MB.
  A lot of the data overhead comes from json.dumps. This is to build mixed cells.
  The rest is from calculate_checksum.
  Pure Python version (with calculate_checksum and dumps) is at 6.3 ms / MB,
  so the rest of the data overhead is fine!

- Database upload overhead is about the same (7 ms / MB) with a flatfile backend
  Database download is almost free.

- A structured cell auth operation is about 10 ms.

- map-list macro evaluation is cheap, 5 ms per (parallel) transformation

- re-translation is about 20 ms per transformation (on top of the macro)

- expression evaluation is about 10 ms + 0.5 ms / MB (of input + output) per transformation
  (speculative relationship!)

- BUT: Non-linear scaling:
  between 100 and 1000 parallel transformations, a x4 slowdown is observed for the last three overheads above.


NOTE: Mixed-to-str conversion is expensive, don't do it!



"""

import sys
import seamless

import seamless.core.execute
seamless.core.execute.DIRECT_PRINT = True

seamless.database_sink.connect()
seamless.database_cache.connect()
#seamless.set_ncores(2)
#seamless.set_parallel_evaluations(5)

seamless.set_ncores(8) ###
seamless.set_parallel_evaluations(100)  ###

# for the big testing, 20 evaluations
seamless.set_parallel_evaluations(20)  ###

"""
import logging
logging.basicConfig()
logging.getLogger("seamless").setLevel(logging.DEBUG)
"""

from seamless.highlevel import Context, Cell, Macro
from seamless.highlevel.library import LibraryContainer

import time
import cProfile
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
sctx.a = Cell("mixed")
sctx.b = Cell("mixed")
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
# Not having a DB at all is also 13 secs, so DB request communication (without upload) doesn't cost much.

repeat = int(10e6)
#repeat = int(5)
#for n in range(1000): # 2x10 GB
#for n in range(100): # 2x1 GB
for n in range(1000):
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
ctx.data_a.set_checksum("d07050610c50de8c810aa1d1e322786ed8932cf6eafa0fbe1f132b2c881af9c2")
ctx.data_b.set_checksum("374c02504f89ed0a760b03c3e1fd2258988576b919d763254709b66fc7bfb22e")
ctx.compute()

"""

#
### For repeat=10 million, 1000 items
### ctx.data_a.set_checksum("fa4e6aa7e7edaa6feb036fd5e8c28ffc48575cefc332187552c5be4bf0511af8")
### ctx.data_b.set_checksum("2988c44780790e4ffceb1f97391e475f165e316f27a656957282a2998aee9d4f")

### For repeat=10 million, 200 items
### ctx.data_a.set_checksum("d07050610c50de8c810aa1d1e322786ed8932cf6eafa0fbe1f132b2c881af9c2")
### ctx.data_b.set_checksum("374c02504f89ed0a760b03c3e1fd2258988576b919d763254709b66fc7bfb22e")

### For repeat=10 million
### ctx.data_a.set_checksum("983730afb7ab41d524b72f1097daaf4a3c15b98943291f96e523730849cabe8c")
### ctx.data_b.set_checksum("46dabc02b59be44064a9e06dd50bc6841833578c2b6339fbc43f090cc17831fa")

### For repeat=5
### ctx.data_a.set_checksum("9b4a551a6c1c5830d6070b9c22ae1788b9743e9637be47d56103bcda019a897c")
### ctx.data_b.set_checksum("9820f1ab795db7b0d195f21966ecb071d76e9ce2fd3a90845974a3905584eb3e")
ctx.compute()

"""
If there is no database (100 x repeat 10e6):
- 13 secs up to here (6.5 ms per MB)
- 0.5 secs to evaluate the macro
- 2.3 secs (2.8 - 0.5) for re-translation (23 ms per transformer)
- 32 secs total time, which leaves 32 - 13 - 0.5 = 18.5 secs for transformation and expression evaluation
  Since 13 secs is required for calculate checksum and decoding, that means ~5.5 secs (55 ms per transformer) overhead
  This is a supplement of 32 ms over just re-translation

If there is no database (100 x repeat 5):
- 2.3 secs up to here (12 ms per auth operation)
- Still 0.5 secs to evaluate the macro
- Still 2.3 secs (2.8 - 0.5) for re-translation (23 ms per transformer, independent of data size!)
- 6.2 secs total time, which leaves 6.2 - 2.3 - 0.5 = 3.5 secs for transformation and expression evaluation
  This is an overhead of 35 ms per transformer, a supplement of just 12 ms over re-translation
  The 20 ms reduction compared to above comes from not handling 2x10 MB of input and 20 MB of output,
  so that's 0.5 ms/MB.

If there is no database (1000 x repeat 5):
- 11.7 secs up to here (12 ms per auth operation). So scales linearly.
- 6.5 secs to evaluate the macro, so scales about linearly
- 98 secs (104.5 - 6.5) for re-translation, which is 4x slower than above  (98 ms)
- 145 secs total time, which leaves 145 - 11.7 - 6.5 = 127 secs for transformation and expression evaluation
  This is an overhead of 127 ms per transformer, which is 4x slower than above (127 ms).
  => So in principle, 90 sconds slower than might be
    - Some 45 secs is await-upon-connection-tasks, this could be optimized?
    - 12 seconds from isinstance is probably unavoidable
    - 9 seconds comes from validate deep structure, that may be unavoidable
    - 5 seconds each from taskmanager.add_task (61k tasks) and asyncio.Task.done (119 million tasks). Avoidable?
  => do maplist-inside-maplist

If the database has not been filled:
- 27.5 secs up to here
If the database has been filled:
- 14 secs up to here: to synthesize the data, and to verify that all is present
  So the raw upload is 13.5 seconds (27.5 - 14); and communication with the DB delays only 1 sec.
- 1.5 secs up to here, with the above elision.

With the database:
- 1.5 secs to evaluate the macro (DB slows down!)
- 5.5 secs for re-translation
- 45.7 secs total time, which leaves 45.7 - 5.5 - 1.5 = 38.5 secs for transformation and expression evaluation
  Compare this to the 18.5 secs w/o database, this is a loss of 20 secs.
  But we have to count the download of the inputs and upload of the results.
  When removing the tfr entries from the database, transformations will be repeated, but no buffers will be uploaded,
  as the sink knows them already.
  This brings total time down to 32 secs, the same as no database!
  So all of the extra overhead is from upload, and download is almost free. (This could be hard disk caching, though)
- 5.5 secs total time with pulling transformation results out of the DB. Again, download is almost free.


Big test with the database (1000 x repeat 10e6):
- Total time 940 secs. Data upload overhead should be ~120 secs, and Seamless data overhead should be ~140 secs.
- 142 secs for re-translation + macro evaluation (142 ms / transformation), a factor 6 slowdown
- 940 - 142 - 120 - 140 = ~540 secs for evaluation
   I.e. 540 ms per transformation. If the same slowdown applies, it would have been 90.
   But we would have expected 30. So a larger slowdown (fewer parallel expressions may have been a cause too)
"""

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

import pstats
sortby = 'tottime'
ps = pstats.Stats(cProfile.profiler).sort_stats(sortby)
ps.print_stats(40)

t0 = time.time()
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
"""
ctx.translate(force=True)
ctx.compute()
print(time.time()-t0)
"""