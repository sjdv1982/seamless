from seamless import macro
from collections import OrderedDict

@macro(OrderedDict((
    ("period", {"type": "float", "default": 0}),
)), with_context=False)
def timer(period):
    from seamless import reactor
    timer = reactor({
        "period": {"pin": "input", "dtype": "float"},
        "trigger": {"pin": "output", "dtype": "signal"}
    })
    timer.code_start.cell().fromfile("cell-timer.py")
    timer.code_update.cell().set("")
    timer.code_stop.cell().set("t.cancel(); dead = True")
    if period > 0:
        timer.period.cell().set(period)
    return timer
