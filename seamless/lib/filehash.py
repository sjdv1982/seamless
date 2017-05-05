from seamless import macro

@macro("str")
def filehash(ctx, filepath):
    from seamless import reactor, pythoncell
    ctx.cell_filehash = pythoncell().fromfile("cell-filehash-start.py")
    reactor_params = {
        "filepath": {
            "pin": "input",
            "dtype": "str",
        },
        "latency": {
            "pin": "input",
            "dtype": "float",
        },
        "filehash": {
            "pin": "output",
            "dtype": "str",
        },
    }
    rc = ctx.rc = reactor(reactor_params)

    ctx.cell_filehash.connect(rc.code_start)
    rc.filepath.cell().set(filepath)
    rc.latency.cell().set(1)
    rc.code_update.cell().set("")
    rc.code_stop.cell().set('terminate.set(); t.join()')
    ctx.export(rc, ["filehash"])
