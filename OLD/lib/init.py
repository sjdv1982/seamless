def init():
    from seamless import reactor
    rc = reactor({
        "trigger": {"pin": "output", "dtype": "signal"}
    })
    rc.code_start.cell().set("PINS.trigger.set()")
    rc.code_update.cell().set("")
    rc.code_stop.cell().set("")
    return rc
