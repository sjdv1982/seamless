import os
os.environ["SEAMLESS_COMMUNION_ID"] = "jobmaster"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:8602"
import seamless
seamless.set_ncores(0)

from seamless import communion_server
communion_server.configure_master(
    buffer=True,
    buffer_status=True,
    transformation_job=True,
    transformation_status=True
)

from seamless.highlevel import load_graph
import sys, json

infile, outfile = sys.argv[1:]
graph = json.load(open(infile))

seamless.database_cache.connect()
seamless.communion_server.start()

ctx = load_graph(graph)

import asyncio
done = asyncio.sleep(1)
asyncio.get_event_loop().run_until_complete(done)

ctx.compute()

colored_graph = ctx.get_graph()
with open(outfile, "w") as f:
    json.dump(colored_graph, f, indent=2, sort_keys=True)