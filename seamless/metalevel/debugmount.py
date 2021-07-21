"""
Mounts transformers in full debug mode

ctx and tf are low level contexts! 
ctx is the root


TODO: module pins! 
- mount as directory
- Python: set the file names correctly 
"""

import os, tempfile, shutil, functools
from seamless.core.manager import livegraph
SEAMLESS_DEBUGGING_DIRECTORY = os.environ.get("SEAMLESS_DEBUGGING_DIRECTORY")

class DebugMount:
    def __init__(self, tf, path):
        self.tf = tf
        self.path = path
        self.mount_ctx = None
    def mount(self, skip_pins):
        from ..core.context import context
        from ..core.macro_mode import macro_mode_on
        from ..core.cell import celltypes, subcelltypes, extensions
        tf = self.tf
        manager = tf._get_manager()
        livegraph = manager.livegraph
        upstreams = livegraph.transformer_to_upstream[tf]
        with macro_mode_on():
            self.mount_ctx = context(toplevel=True)
            for pinname, pin in tf._pins.items():
                if pinname in skip_pins:
                    continue            
                celltype = pin.celltype
                subcelltype = pin.subcelltype
                if celltype is None:                
                    pin_cells = manager.cell_from_pin(pin)
                    if len(pin_cells) == 0:
                        celltype = "mixed"
                    else:
                        celltype = pin_cells[0].celltype
                        subcelltype = pin_cells[0]._subcelltype
                if celltype == "module":
                    raise NotImplementedError
                if subcelltype is not None:
                    cellclass = subcelltypes[subcelltype]
                else:
                    cellclass = celltypes[celltype]
                c = cellclass()
                ext = extensions[cellclass]
                filename = os.path.join(self.path, pinname) + ext
                c.mount(filename, mode="rw", authority="cell", persistent=False)
                setattr(self.mount_ctx, pinname, c)
                checksum = None
                accessor = upstreams.get(pinname)
                if accessor is not None:
                    checksum = accessor._checksum
                print("PIN", pinname, checksum.hex() if checksum is not None else None)
                if checksum is not None:
                    c.set_checksum(checksum.hex())
        for pinname, pin in tf._pins.items():
            c = getattr(self.mount_ctx, pinname)
            c._set_observer(functools.partial(self._observe, pinname), False)

    def _observe(self, pinname, value):
        print("OBS", pinname, value)
        # ...

    def destroy(self):
        self.mount_ctx.destroy()
        shutil.rmtree(self.path, ignore_errors=True)

class DebugMountManager:
    def __init__(self):
        self._mounts = {}

    def add_mount(self, tf, skip_pins=[]):
        #print("ADD MOUNT", tf)
        if SEAMLESS_DEBUGGING_DIRECTORY is None:
            raise Exception("SEAMLESS_DEBUGGING_DIRECTORY undefined")
        path = tempfile.mkdtemp(dir=SEAMLESS_DEBUGGING_DIRECTORY)
        mount = DebugMount(tf, path)
        self._mounts[tf] = mount
        mount.mount(skip_pins=skip_pins)
        return mount

    def remove_mount(self, mount):
        tf = mount.tf
        self._mounts.pop(tf)
        mount.destroy()

    def is_mounted(self, tf):
        return tf in self._mounts

    def remove_mounts(self, ctx):
        #print("REMOVE MOUNTS", hex(id(ctx)))
        for tf in list(self._mounts.keys()):
            if tf._root() is not ctx:
                continue
            self.remove_mount(self._mounts[tf])

debugmountmanager = DebugMountManager()            