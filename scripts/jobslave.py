import os
import asyncio
import sys

import argparse
parser = argparse.ArgumentParser(description="""Communion jobslave.

The environmental variables SEAMLESS_COMMUNION_OUTGOING_PORT
and SEAMLESS_COMMUNION_OUTGOING_IP must have been defined.
""")
parser.add_argument("--time",type=float,default=None)
parser.add_argument("--ncores",type=int,default=None)
parser.add_argument("--communion_id",type=str,default="serve_graph", help="Name of this peer in the communion")
parser.add_argument(
    "--database",
    help="""Connect to a Seamless database server.
The environmental variables SEAMLESS_DATABASE_IP 
and SEAMLESS_DATABASE_PORT must have been defined
""",
    action="store_true"
)
parser.add_argument(
    "--interactive",
    help="Do not enter a mainloop. Assumes that the script was opened with an interactive shell (e.g. ipython -i)",
    action="store_true"
)
parser.add_argument("--direct-print", dest="direct_print", action="store_true")
parser.add_argument(
    "--debug",
    help="Serve graph in debugging mode. Turns on asyncio debugging, and sets the Seamless logger to DEBUG",
    action="store_true"
)
args = parser.parse_args()

env = os.environ

env["SEAMLESS_COMMUNION_ID"] = args.communion_id

if args.debug:
    import asyncio
    asyncio.get_event_loop().set_debug(True)
    import logging
    logging.basicConfig()
    logging.getLogger("seamless").setLevel(logging.DEBUG)

import seamless

if args.database:
    seamless.database_sink.connect()
    seamless.database_cache.connect()

from seamless import communion_server

if args.ncores is not None and args.ncores > 0:
    seamless.set_ncores(args.ncores)

if args.direct_print:
    import seamless.core.execute
    seamless.core.execute.DIRECT_PRINT = True

communion_server.configure_servant(
    buffer=True,
    buffer_status=True,
    transformation_job=True,
    transformation_status=True,
    clear_exception=True,
    hard_cancel=True,
)
port=os.environ["SEAMLESS_COMMUNION_OUTGOING_PORT"]
ip=os.environ["SEAMLESS_COMMUNION_OUTGOING_IP"]
communion_server.start()

from seamless.core import context
ctx = context(toplevel=True)

loop = asyncio.get_event_loop()
if args.time:
    loop.call_later(args.time, sys.exit)

if not args.interactive:
    loop.run_forever()