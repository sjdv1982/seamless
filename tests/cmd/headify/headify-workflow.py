import traceback
import argparse
import time

parser = argparse.ArgumentParser()
parser.add_argument("input", help="Input file to headify")
parser.add_argument(
    "-n", "--lines", help="Select the first n lines", type=int, default=10, dest="lines",
    required=True, # added
)

parser.add_argument(
    "--sleep",
    help="Sleep for X seconds after execution",
    type=float,
    required=True, # added
)
args = parser.parse_args()

import seamless
seamless.delegate()

from seamless import Transformer, Context, Cell

try:
    Transformer.from_canonical_interface(
        tool="canonical-interface/headify"
    )
except ValueError:
    traceback.print_exc(0)

tf = Transformer.from_canonical_interface(
    tool="canonical-interface/headify",
    command="headify infile -n $lines --sleep $sleep"
)
ctx = Context()
ctx.tf = tf
ctx.compute()

t = time.time()
ctx.infile = Cell("bytes")
tf.infile = ctx.infile
with open(args.input, "rb") as f:
    ctx.infile = f.read()
tf.lines = args.lines
tf.sleep = args.sleep
ctx.compute()
print(ctx.status)
print(ctx.tf.exception)

print("{:.1f} seconds elapsed".format(time.time()-t))
