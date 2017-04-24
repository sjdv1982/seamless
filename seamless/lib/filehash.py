
@macro("str", with_context=False)
def filehash(filepath):
    from seamless import reactor
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
    rc = reactor(reactor_params)

    rc.cell_filehash.connect(rc.code_start)
    rc.code_update.set("stop(); start()")
    rc.cell_filehash_stop.connect(rc.code_stop)
    return rc
