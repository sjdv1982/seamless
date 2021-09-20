"""
Mounts transformers in full debug mode

ctx and tf are low level contexts! 
ctx is the root


TODO: module pins! 
- mount as directory
- Python: set the file names correctly 
"""

from logging import warn
import os, tempfile, shutil, functools
from sys import modules
from seamless.core.protocol.calculate_checksum import calculate_checksum_sync
from seamless.core.protocol.serialize import serialize_sync
from seamless.core.protocol.deserialize import deserialize_sync
from seamless.core.manager import livegraph

SEAMLESS_DEBUGGING_DIRECTORY = os.environ.get("SEAMLESS_DEBUGGING_DIRECTORY")

def pull_module(pinname, upstreams, manager):
    accessor = upstreams.get(pinname)
    checksum = None
    if accessor is not None: #unconnected
        checksum = accessor._checksum
    if checksum is not None:
        checksum2 = checksum.hex()
        buffer = manager.resolve(checksum2)
        if buffer is not None:
            mod_def = deserialize_sync(buffer,checksum, "plain", True)
            try:
                mod_lang = mod_def["language"]
                mod_type = mod_def["type"]
                mod_code = mod_def["code"]
            except Exception:
                mod_lang, mod_type, mod_code = None, None, None
    return mod_lang, mod_type, mod_code, checksum

def analyze_mod_code(mod_code, pinname):
    if mod_code is not None and not isinstance(mod_code, str):
        if isinstance(mod_code, dict):
            msg = "Module '{}' seems to contain a multi-module definition, not writing to file"
        else:
            msg = "Module '{}' contains an unknown data type, not mounting, not writing to file"
        print(msg.format(pinname))
        mod_code = None
    return mod_code

class DebugMount:
    def __init__(self, tf, path):
        self.tf = tf
        self.path = path
        self.mount_ctx = None
        self.result_pinname = None
        self._pulling = False
        self._modules = {}
    def mount(self, skip_pins):
        from ..core.context import context
        from ..core.macro_mode import macro_mode_on
        from ..core.cell import celltypes, subcelltypes, extensions, cell as core_cell
        from ..mime import language_to_extension
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
                if subcelltype == "module":
                    mod_lang, mod_type, mod_code, mod_cs = pull_module(
                        pinname, upstreams, manager
                    )
                    if mod_lang is None:
                        msg = "Module '{}' has unknown language, mounting to .txt file"
                        print(msg.format(pinname))
                        ext = ".txt"
                    else:
                        ext = "." + language_to_extension(mod_lang, "txt")
                    mod_code = analyze_mod_code(mod_code, pinname)
                    self._modules[pinname] = mod_lang, mod_type, mod_cs
                    c = core_cell("text")                    
                else:
                    if subcelltype is not None:
                        cellclass = subcelltypes[subcelltype]
                    else:
                        cellclass = celltypes[celltype]
                    c = cellclass()
                    ext = extensions[cellclass]
                filename = os.path.join(self.path, pinname) + ext
                mode = "w" if pinname == self.result_pinname else "rw"
                c.mount(
                    filename, mode=mode, 
                    authority="cell", persistent=False
                )
                setattr(self.mount_ctx, pinname, c)
                if subcelltype == "module":
                    if mod_code is not None:
                        c.set(mod_code)
                else:
                    checksum = None
                    accessor = upstreams.get(pinname)
                    if accessor is not None:
                        checksum = accessor._checksum
                    if checksum is not None:
                        c.set_checksum(checksum.hex())
        for pinname, pin in tf._pins.items():
            if pinname != self.result_pinname:
                c = getattr(self.mount_ctx, pinname)
                c._set_observer(functools.partial(self._observe, pinname), False)

    def _observe(self, pinname, checksum):
        if self._pulling:
            return
        if pinname in self._modules:
            from ..core.protocol.get_buffer import get_buffer
            code = None
            if checksum is not None:
                checksum2 = bytes.fromhex(checksum)
                code_buf = get_buffer(checksum2)
                if code_buf is not None:
                    code = deserialize_sync(code_buf, checksum2, "text", True)
            mod_lang, mod_type, _ = self._modules[pinname]
            new_value = {
                "language": mod_lang,
                "type": mod_type,
            }
            if code is not None:
                new_value["code"] = code
            new_value_buffer = serialize_sync(new_value, "plain")
            new_checksum = calculate_checksum_sync(new_value_buffer)
            self._modules[pinname] = mod_lang, mod_type, new_checksum
        self._transformer_update()

    def _transformer_update(self):
        from ..core.manager.tasks.transformer_update import TransformerUpdateTask
        transformer = self.tf
        manager = transformer._get_manager()
        manager.taskmanager.cancel_transformer(transformer)
        manager.cachemanager.transformation_cache.cancel_transformer(transformer, False)
        TransformerUpdateTask(manager, transformer).launch()

    def pull(self):
        try:
            self._pulling = True
            transformer = self.tf
            manager = transformer._get_manager()
            livegraph = manager.livegraph
            upstreams = livegraph.transformer_to_upstream[transformer]
            
            for pinname, accessor in upstreams.items():
                if pinname in self._modules:
                    mod_lang, mod_type, mod_code, mod_cs = pull_module(
                        pinname, upstreams, manager
                    )
                    mod_code = analyze_mod_code(mod_code, pinname)
                    self._modules[pinname] = mod_lang, mod_type, mod_cs
                    if mod_code is not None:
                        c = getattr(self.mount_ctx, pinname)
                        c.set(mod_code)
                else:      
                    checksum = None
                    if accessor is not None: #unconnected
                        checksum = accessor._checksum
                    if checksum is not None:
                        checksum = checksum.hex()
                    c = getattr(self.mount_ctx, pinname)
                    c.set_checksum(checksum)
            self._pulling = False            
            self._transformer_update()
        finally:
            self._pulling = False            

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
            pin = transformer._pins[pinname]
            if pinname in mount._modules:
                _, _, checksum = mount._modules[pinname]
            else:
                c = getattr(mount_ctx, pinname)
                checksum = c._checksum
            input_pins[pinname] = checksum 
            celltype, subcelltype = pin.celltype, pin.subcelltype
            if celltype is None:
                celltype, subcelltype = c.celltype, c._subcelltype 
            celltypes[pinname] = celltype, subcelltype

            if checksum is None:
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