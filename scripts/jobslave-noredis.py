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
args = parser.parse_args()

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
    loop.call_later(sys.exit)
loop.run_forever()