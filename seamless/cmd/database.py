import os

if "SEAMLESS_DATABASE_IP" not in os.environ:
    os.environ["SEAMLESS_DATABASE_IP"] = "localhost"
if "SEAMLESS_DATABASE_PORT" not in os.environ:
    os.environ["SEAMLESS_DATABASE_PORT"] = "5522"

# TODO: local mode database ("rprod --database")

# HACK 
if "SEAMLESS_COMMUNION_IP" not in os.environ:
    os.environ["SEAMLESS_COMMUNION_IP"] = "localhost"
if "SEAMLESS_COMMUNION_PORT" not in os.environ:
    os.environ["SEAMLESS_COMMUNION_PORT"] = "5533"

import sys; print("HACK: communion", file=sys.stderr)
import seamless
seamless.set_ncores(0)
from seamless import communion_server

communion_server.configure_master(
    transformation_job=True,
    transformation_status=True,
)

communion_server.start()
#/HACK

from seamless import database_cache, database_sink

database_cache.connect()
database_sink.connect()

def set_buffer(checksum, buffer):
    database_sink.set_buffer(checksum, buffer, persistent=False)


def need_buffer(checksum):
    return not database_sink.has_buffer(checksum)


def has_buffer(checksum):
    return database_cache.has_buffer(checksum)


_ = None  # STUB
