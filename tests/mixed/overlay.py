import sys
import numpy as np
from seamless.mixed.MixedDict import mixed_dict
from seamless.mixed.OverlayMonitor import OverlayMonitor

import json

_print = print
def print(*args):
    for a in args:
        _print(json.dumps(a, indent=2, sort_keys=True), end=" ")
    _print()

data, storage, form = {}, {}, {}

inchannels = {}
d = mixed_dict(data, storage, MonitorClass=OverlayMonitor, inchannels=inchannels)
monitor = d._monitor

d["a"] = 10
#monitor.set_path(("a",), 10)
