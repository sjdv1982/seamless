
import os
import argparse
import sys

parser = argparse.ArgumentParser(
    description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
)
parser.add_argument("input", help="Input file to headify")
parser.add_argument(
    "-n", "--lines", help="Select the first n lines", type=int, default=10, dest="lines"
)
parser.add_argument(
    "--batch", help="Interpret the input as a list of files", action="store_true"
)

parser.add_argument(
    "--sleep",
    help="Sleep for X seconds after execution",
    type=int,
)

args = parser.parse_args()

def get_output_file(input_file):
    root, ext = os.path.splitext(input_file)
    return root + "-head" + ext

# The batch section is identical to the previous interface.
#  headify_lib.py is added explicitly because the .yaml file no longer does.
if args.batch:
    if not os.path.exists(args.input):
        print("{}")
        exit(0)
    input_files = [args.input, "./headify_lib.py"]
    result_files = []
    input_dir = os.path.dirname(args.input)
    with open(args.input) as inpf:
        for input_file0 in inpf:
            input_file = os.path.join(input_dir, input_file0.strip())
            input_files.append(input_file)
            result_files.append(get_output_file(input_file))
else:
    input_files = [
        {
            "name": "infile",
            "mapping": args.input
        },
        {
            "name": "headify",
            "mapping": sys.argv[0][:-len(".SEAMLESS.py")]
        },
        {
            "name": "headify_lib.py",
            "mapping": os.path.join(os.path.dirname(sys.argv[0]), "headify_lib.py")
        },

    ]
    result_files = {
        "infile-head": get_output_file(args.input)
    }

#############################################################

interface = {
    "files": input_files,
    "results": result_files,
}

import json
print(json.dumps(interface))