import sys
import numpy as np
from seamless.mixed.MixedDict import mixed_dict, get_form_dict
from seamless.mixed.OverlayMonitor import OverlayMonitor
import json

_print = print
def print(*args):
    for a in args:
        _print(json.dumps(a, indent=2, sort_keys=True), end=" ")
    _print()

data = {}
storage, form = get_form_dict(data)
inchannels = {}

d = mixed_dict(data, storage, form,
    inchannels=inchannels, MonitorClass=OverlayMonitor)
monitor = d._monitor

d["a"] = 10
print(data)

monitor.add_inchannel(("b","c"))
monitor.receive_inchannel_value(("b","c"), 80)
print(data)

d["b"] = 6
print(data)

monitor.add_inchannel(("b","c"))
d["b"] = 6
print(data)
