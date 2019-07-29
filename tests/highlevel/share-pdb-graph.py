import seamless
from seamless.highlevel import load_graph
import sys, json

try:
    import seamless
    redis_sink = seamless.RedisCache()
    import asyncio
    asyncio.get_event_loop().run_until_complete(asyncio.sleep(0.5))
    redis_sink.connection.info()
except Exception:
    print("No Redis found! Exiting...")
    import sys; sys.exit()

graph = json.load(open("share-pdb.seamless"))

ctx = load_graph(graph)
ctx.equilibrate()

ctx.bb_pdb.share()
ctx.pdb.share()
ctx.code.share()
ctx.code.mount("/tmp/code.bash")
ctx.translate(force=True)