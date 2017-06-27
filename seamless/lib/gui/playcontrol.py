from seamless import macro
@macro("str")
def playcontrol(ctx, title):
    from seamless import reactor
    ctx.playcontrol = reactor({
        "min": {"pin": "input", "dtype": "int"},
        "max": {"pin": "input", "dtype": "int"},
        "rate": {"pin": "input", "dtype": "int"},
        "value": {"pin": "edit", "dtype": "int"},
        "loop": {"pin": "edit", "dtype": "bool"},
        "title": {"pin": "input", "dtype": "str"},
    })
    ctx.playcontrol.code_start.cell().fromfile("cell-playcontrol.py")
    ctx.playcontrol.code_update.cell().set("do_update()")
    ctx.playcontrol.code_stop.cell().set("widget.destroy()")

    ctx.playcontrol.title.cell().set(title)
    ctx.playcontrol.min.cell().set(1)
    ctx.playcontrol.rate.cell().set(2)
    ctx.playcontrol.loop.cell().set(True)
    ctx.export(ctx.playcontrol, forced=["min", "rate", "loop"])
