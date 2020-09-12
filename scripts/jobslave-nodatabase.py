import os
os.environ["SEAMLESS_COMMUNION_ID"] = "jobslave"
os.environ["SEAMLESS_COMMUNION_OUTGOING"] = "8602"
os.environ["SEAMLESS_COMMUNION_INCOMING"] = "localhost:8600"
import seamless
import asyncio
import sys
from seamless import communion_server

import argparse
parser = argparse.ArgumentParser()
parser.add_argument("--time",type=float,default=None)
parser.add_argument("--ncores",type=int,default=None)
parser.add_argument("--communion_id",type=str,default="jobslave")
parser.add_argument("--communion_outgoing",type=int, default=8602)
parser.add_argument("--communion_incoming",type=str)
parser.add_argument(
    "--interactive",
    help="Do not enter a mainloop. Assumes that the script was opened with an interactive shell (e.g. ipython -i)",
    action="store_true"
)
parser.add_argument(
    "--direct-print",
    dest="direct_print",
    help="Print stdout and stderr of transformers directly on the console",
    action="store_true"
)

parser.add_argument(
    "--debug",
    help="Serve graph in debugging mode. Turns on asyncio debugging, and sets the Seamless logger to DEBUG",
    action="store_true"
)

args = parser.parse_args()

if args.direct_print:
    import seamless.core.execute
    seamless.core.execute.DIRECT_PRINT = True

if args.debug:
    import asyncio
    asyncio.get_event_loop().set_debug(True)
    import logging
    logging.basicConfig()
    logging.getLogger("seamless").setLevel(logging.DEBUG)

env = os.environ


env["SEAMLESS_COMMUNION_ID"] = args.communion_id
if args.communion_outgoing not in (None,"","None"):
    env["SEAMLESS_COMMUNION_OUTGOING"] = str(args.communion_outgoing)
if args.communion_incoming is not None:
    env["SEAMLESS_COMMUNION_INCOMING"] = args.communion_incoming

if args.ncores is not None and args.ncores > 0:
    seamless.set_ncores(args.ncores)

communion_server.configure_servant(
    buffer=True,
    buffer_status=True,
    transformation_job=True,
    transformation_status=True,
    clear_exception=True,
    hard_cancel=True,
)

from seamless.core import context
ctx = context(toplevel=True)

loop = asyncio.get_event_loop()
if args.time:
    loop.call_later(args.time, sys.exit)

if not args.interactive:
    loop.run_forever()
