import sys
import numpy as np
from seamless.mixed.mixed_dict import mixed_dict
from seamless.mixed.OverlayMonitor import OverlayMonitor

import json

_print = print
def print(*args):
    for a in args:
        _print(json.dumps(a, indent=2, sort_keys=True), end=" ")
    _print()

data, storage, form = {}, {}, {}

d = mixed_dict(data, storage, OverlayMonitor)
monitor = d._monitor
