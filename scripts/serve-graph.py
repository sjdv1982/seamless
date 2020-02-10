import sys, argparse
parser = argparse.ArgumentParser()
parser.add_argument("graph",help="Seamless graph file to serve")
parser.add_argument("zipfile",help="Zip file that contains the buffers of the graph checksum", nargs='?')
parser.add_argument(
    "--redis",
    help="Connect to a Redis instance",
    action="store_true"
)
parser.add_argument(
    "--interactive",
    help="Do not enter a mainloop. Assumes that the script was opened with an interactive shell (e.g. ipython -i)",
    action="store_true"
)
parser.add_argument(
    "--debug",
    action="store_true"
)

args = parser.parse_args()

if args.zipfile is None and not args.redis:
    print("If no zipfile is specified, --redis must be enabled", file=sys.stderr)
    sys.exit(1)

if args.debug:
    import asyncio
    asyncio.get_event_loop().set_debug(True)

import seamless, seamless.shareserver
import sys, os, json, subprocess
env = os.environ
shareserver_address = env.get("SHARESERVER_ADDRESS")
if shareserver_address is not None:
    if shareserver_address == "HOSTNAME":
        shareserver_address = subprocess.getoutput("hostname -I | awk '{print $1}'")
    seamless.shareserver.DEFAULT_ADDRESS = shareserver_address
    print("Setting shareserver address to: {}".format(shareserver_address))
    

from seamless.highlevel import load_graph
graph = json.load(open(args.graph))
ctx = load_graph(graph, mounts=False, shares=True)
if args.zipfile is not None:
    ctx.add_zip(args.zipfile)
if args.redis:
    params = {}    
    redis_host = env.get("REDIS_HOST")
    if redis_host is not None:
        params["host"] = redis_host
    redis_port = env.get("REDIS_PORT")
    if redis_port is not None:
        params["port"] = redis_port
    redis_sink = seamless.RedisSink(**params)
    redis_cache = seamless.RedisCache(**params)
ctx.translate()

import asyncio
asyncio.get_event_loop().run_forever()