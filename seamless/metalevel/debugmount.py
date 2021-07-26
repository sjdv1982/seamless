"""
Mounts transformers in full debug mode

ctx and tf are low level contexts! 
ctx is the root


TODO: module pins! 
- mount as directory
- Python: set the file names correctly 
"""

import os, tempfile, shutil, functools

SEAMLESS_DEBUGGING_DIRECTORY = os.environ.get("SEAMLESS_DEBUGGING_DIRECTORY")

class DebugMount:
    def __init__(self, tf, path):
        self.tf = tf
        self.path = path
        self.mount_ctx = None
        self.result_pinname = None
    def mount(self, skip_pins):
        from ..core.context import context
        from ..core.macro_mode import macro_mode_on
        from ..core.cell import celltypes, subcelltypes, extensions
        tf = self.tf
        manager = tf._get_manager()
        livegraph = manager.livegraph
        upstreams = livegraph.transformer_to_upstream[tf]
        for pinname, pin in tf._pins.items():
            if pin.io == "output":
                self.result_pinname = pinname
                break
        else:
            raise Exception
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
                mode = "w" if pinname == self.result_pinname else "rw"
                c.mount(filename, mode=mode, authority="cell", persistent=False)
                setattr(self.mount_ctx, pinname, c)
                checksum = None
                accessor = upstreams.get(pinname)
                if accessor is not None:
                    checksum = accessor._checksum
                print("PIN", pinname, checksum.hex() if checksum is not None else None)
                if checksum is not None:
                    c.set_checksum(checksum.hex())
        for pinname, pin in tf._pins.items():
            if pinname != self.result_pinname:
                c = getattr(self.mount_ctx, pinname)
                c._set_observer(functools.partial(self._observe, pinname), False)

    def _observe(self, pinname, value):
        from ..core.manager.tasks.transformer_update import TransformerUpdateTask
        from ..core.status import StatusReasonEnum
        print("OBS", pinname, value)
        transformer = self.tf
        manager = transformer._get_manager()
        manager.taskmanager.cancel_transformer(transformer)
        manager.cachemanager.transformation_cache.cancel_transformer(transformer, False)
        TransformerUpdateTask(manager, transformer).launch()

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

    def taskmanager_has_mounts(self, taskmanager):
        for tf in list(self._mounts.keys()):
            manager = tf._get_manager()
            if manager.taskmanager is taskmanager:
                return True
        return False

    def debug_result(self, transformer, checksum):
        mount = self._mounts[transformer]
        mount_ctx = mount.mount_ctx
        result = getattr(mount_ctx, mount.result_pinname)
        checksum2 = checksum.hex() if checksum is not None else None
        result.set_checksum(checksum2)

    async def run(self, transformer):
        mount = self._mounts[transformer]
        mount_ctx = mount.mount_ctx
        input_pins = {}
        celltypes = {}
        for pinname in transformer._pins:
            if pinname == "META":
                continue
            if pinname == mount.result_pinname:
                continue
            c = getattr(mount_ctx, pinname)
            checksum = c._checksum
            input_pins[pinname] = checksum 
            celltypes[pinname] = c.celltype, c._subcelltype
            if checksum is None:
                print("NOT OK", pinname)
                ok = False
                break
        else:
            ok = True
        if not ok:
            self.debug_result(transformer, None)
            return
        result_cell = getattr(mount_ctx, mount.result_pinname)
        outputpin = mount.result_pinname, result_cell.celltype, result_cell._subcelltype
        manager = transformer._get_manager()
        transformation_cache = manager.cachemanager.transformation_cache
        await transformation_cache.update_transformer(
            transformer, celltypes, input_pins, outputpin
        )

debugmountmanager = DebugMountManager()            