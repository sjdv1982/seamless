import sys, os, json, subprocess, argparse
parser = argparse.ArgumentParser()
parser.add_argument(
    "graph",
    help="Seamless graph file to serve",
    type=argparse.FileType('r')
)
parser.add_argument(
    "zipfile",
    help="""Zip file that contains the buffers of the graph checksum.
If not provided, the buffers must be read from the database or a communion peer""",
    nargs='?',
    type=argparse.FileType('rb')
)
parser.add_argument(
    "--database",
    help="""Connect to a Seamless database server.
The environmental variables SEAMLESS_DATABASE_IP 
and SEAMLESS_DATABASE_PORT must have been defined.
""",
    action="store_true"
)

parser.add_argument(
    "--communion",
    help="""Connect to a Seamless communion peer, e.g. jobless or a jobslave.
The environmental variables SEAMLESS_COMMUNION_IP 
and SEAMLESS_COMMUNION_PORT must have been defined.
Alternatively, a list of comma-separated communion server URLs 
can be defined using SEAMLESS_COMMUNION_INCOMING.

Note that serve-graph does not provide any buffers to communion peers.
Communion peers must therefore connect to a database or to another peer.
""",
    action="store_true"
)
parser.add_argument("--communion_id",type=str,default="serve_graph", help="Name of this peer in the communion")
parser.add_argument(
    "--interactive",
    help="Do not enter a mainloop. Assumes that the script was opened with an interactive shell (e.g. ipython -i)",
    action="store_true"
)
parser.add_argument(
    "--debug",
    help="Serve graph in debugging mode. Turns on asyncio debugging, and sets the Seamless logger to DEBUG",
    action="store_true"
)

parser.add_argument(
    "--status-graph",
    help="Bind a graph that reports the status of the main graph",
    type=argparse.FileType('r')
)

parser.add_argument(
    "--add-zip",
    help="Specify additional zip files to be added",
    type=argparse.FileType('rb'),
    action="append",
    default=[],
)

parser.add_argument("--ncores",type=int,default=None)

parser.add_argument(
    "--shares",
    help="Share cells over the network as specified in the graph file(s)",
    default=True,
    type=bool
)

parser.add_argument(
    "--mounts",
    help="Mount cells on the file system as specified in the graph file(s)",
    default=False,
    type=bool
)

parser.add_argument(
    "--no-lru",
    dest="no_lru",
    help="Disable LRU caches for checksum-to-buffer, value-to-checksum, value-to-buffer, and buffer-to-value",
    action="store_true"
)

args = parser.parse_args()

if args.zipfile is None and not args.database:
    print("If no zipfile is specified, --database must be enabled", file=sys.stderr)
    sys.exit(1)

if args.debug:
    import asyncio
    asyncio.get_event_loop().set_debug(True)
    import logging
    logging.basicConfig()
    logging.getLogger("seamless").setLevel(logging.DEBUG)

env = os.environ

env["SEAMLESS_COMMUNION_ID"] = args.communion_id

import seamless

if args.no_lru:
    from seamless.core.protocol.calculate_checksum import calculate_checksum_cache, checksum_cache
    from seamless.core.protocol.deserialize import deserialize_cache
    from seamless.core.protocol.serialize import serialize_cache
    calculate_checksum_cache.disable()
    checksum_cache.disable()
    deserialize_cache.disable()
    serialize_cache.disable()

import seamless.shareserver
from seamless import communion_server

if args.communion:
    communion_server.configure_master({
        "buffer": True,
        "buffer_status": True,
        "buffer_info": True,
        "transformation_job": True,
        "transformation_status": True,
        "semantic_to_syntactic": True,
    })

    """
    # will not work until load_graph will be much smarter
    if args.database:
        communion_server.configure_servant({
            "buffer": False,
            "buffer_status": False,
            "buffer_info": False,
            "transformation_job": False,
            "transformation_status": False,
            "semantic_to_syntactic": False,
            "hard_cancel": False,  # allow others to hard cancel our jobs
            "clear_exception": False, # allow others to clear exceptions on our jobs
        })
    """

    communion_server.start()

if args.ncores is not None:
    seamless.set_ncores(args.ncores)

shareserver_address = env.get("SHARESERVER_ADDRESS")
if shareserver_address is not None:
    if shareserver_address == "HOSTNAME":
        shareserver_address = subprocess.getoutput("hostname -I | awk '{print $1}'")
    seamless.shareserver.DEFAULT_ADDRESS = shareserver_address
    print("Setting shareserver address to: {}".format(shareserver_address))

import seamless.highlevel.stdlib

if args.database:
    seamless.database_sink.connect()
    seamless.database_cache.connect()

from seamless.highlevel import load_graph, Context
graph = json.load(args.graph)
if args.zipfile is None and not args.add_zip:
    ctx = load_graph(graph, mounts=args.mounts, shares=args.shares)
else:
    ctx = Context()
    if args.zipfile is not None:
        ctx.add_zip(args.zipfile)
    for zipf in args.add_zip:
        ctx.add_zip(zipf)
    ctx.set_graph(graph, mounts=args.mounts, shares=args.shares)
ctx.translate()

if args.status_graph:
    from seamless.metalevel.bind_status_graph import bind_status_graph
    status_graph = json.load(args.status_graph)
    ctx2 = bind_status_graph(
        ctx, status_graph,
        mounts=False,
        shares=True,
        zips=args.add_zip,
    )

print("Serving graph...")
if not args.interactive:
    print("Press Ctrl+C to end")
    import asyncio
    asyncio.get_event_loop().run_forever()