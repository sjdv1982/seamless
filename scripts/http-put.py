import argparse
import requests
import os
import sys
import json

parser = argparse.ArgumentParser()
parser.add_argument("url",
    help="""Seamless URL to put a value to.
Example: http://localhost:5813/ctx/mycell

This requires a Seamless cell to have been shared with readonly=False,
e.g. ctx.mycell.share(readonly=False)
or   ctx.somecell.share("mycell", readonly=False)
"""
)
parser.add_argument("value",nargs="?",
    help="Value to put"
)

parser.add_argument("--upload-file", dest="upload_file",
    help="File to upload"
)

def err(txt):
    print("error: " + txt, file=sys.stderr)
    exit(1)

args = parser.parse_args()
if args.value is None and args.upload_file is None:
    err("You must specify a file or a value")
if args.value is not None and args.upload_file is not None:
    err("You must specify a file or a value, not both")

if args.value is not None:
    buffer = args.value
else:
    filename = args.upload_file
    if not os.path.exists(filename):
        err("Filename {} does not exist".format(filename))
    with open(filename) as f:
        buffer = f.read()

try:
    r = requests.get(args.url, params={"mode": "marker"})
    marker = r.json()["marker"]
except:
    err("Cannot obtain a marker from specified URL. It may be unreachable, or not a Seamless URL")

headers = {
    "Content-Type": "application/json; charset=utf-8",
}
payload=json.dumps({"buffer": buffer, "marker": marker + 1})
r = requests.put(args.url, data=payload, headers=headers)
if r.status_code != requests.codes.ok:
    print(r.text)
    err("The server yielded the following error reponse code: {}".format(r.status_code))