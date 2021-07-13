_ide = "vscode"  # hard-coded for 0.7

def debug_hook(debug):
    if debug is None:
        return
    if debug.get("python_attach") is not None:
        raise NotImplementedError
    if debug.get("generic_attach") is not None:
        raise NotImplementedError        