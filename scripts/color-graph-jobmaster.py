import os
os.environ["SEAMLESS_COMMUNION_ID"] = "jobmaster"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:8602"
import seamless
seamless.set_ncores(0)

from seamless import communionserver
communionserver.configure_master(
    value=True,
    transformer_job=True,
    transformer_result=True,
    transformer_result_level2=True
)

from seamless.highlevel import load_graph
import sys, json

infile, outfile = sys.argv[1:]
graph = json.load(open(infile))

redis_cache = seamless.RedisCache()

ctx = load_graph(graph)

import asyncio
done = asyncio.sleep(1)
asyncio.get_event_loop().run_until_complete(done)

ctx.equilibrate()

colored_graph = ctx.get_graph()
with open(outfile, "w") as f:
    json.dump(colored_graph, f, indent=2, sort_keys=True)