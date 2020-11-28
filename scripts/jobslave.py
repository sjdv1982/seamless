import os
import asyncio
import sys

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
args = parser.parse_args()

env = os.environ


env["SEAMLESS_COMMUNION_ID"] = args.communion_id
if args.communion_outgoing not in (None,"","None"):
    env["SEAMLESS_COMMUNION_OUTGOING"] = str(args.communion_outgoing)
if args.communion_incoming is not None:
    env["SEAMLESS_COMMUNION_INCOMING"] = args.communion_incoming

import seamless

params = {}
db_host = env.get("SEAMLESS_DATABASE_HOST")
if db_host is not None:
    params["host"] = db_host
db_port = env.get("SEAMLESS_DATABASE_PORT")
if db_port is not None:
    params["port"] = db_port
seamless.database_sink.connect(**params)
seamless.database_cache.connect(**params)

from seamless import communion_server

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