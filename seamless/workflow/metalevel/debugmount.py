"""
Mounts transformers in full debug mode

ctx and tf are low level contexts! 
ctx is the root
"""

from copy import deepcopy
import os, tempfile, shutil, functools

from seamless.checksum.get_buffer import get_buffer
from seamless.checksum.deserialize import deserialize_sync
from seamless.checksum.serialize import serialize_sync
from seamless import Checksum, Buffer
from seamless.checksum.mime import language_to_extension

SEAMLESS_DEBUGGING_DIRECTORY = os.environ.get("SEAMLESS_DEBUGGING_DIRECTORY")

module_tag = "@@MODULE_"


def checksum_to_code(checksum: Checksum):

    code = None
    checksum = Checksum(checksum)
    if checksum:
        code_buf = get_buffer(checksum, remote=False)
        if code_buf is not None:
            code = deserialize_sync(code_buf, checksum, "text", True)
    return code


def parse_kwargs(checksum: Checksum):

    checksum = Checksum(checksum)
    if not checksum:
        return {}
    buf = get_buffer(checksum, remote=False)
    if buf is None:
        return buf
    kwargs = deserialize_sync(buf, checksum, "mixed", True)
    result = {}
    for k, v in kwargs.items():
        vbuf = serialize_sync(v, "mixed")
        vchecksum = Buffer(vbuf).get_checksum()
        result[k] = vchecksum
    return result


def integrate_compiled_module(mod_lang, mod_rest, object_codes):
    new_value = deepcopy(mod_rest)
    new_value["type"] = "compiled"
    if mod_lang is not None:
        new_value["language"] = mod_lang
    for obj_name in object_codes:
        obj_code = object_codes[obj_name]
        pos = obj_name.index(".")
        obj_name2 = obj_name[pos + 1 :]
        assert "objects" in new_value and obj_name2 in new_value["objects"], obj_name2
        new_value["objects"][obj_name2]["code"] = obj_code
    new_value_buffer = serialize_sync(new_value, "plain")
    new_checksum = Buffer(new_value_buffer).get_checksum()
    buffer_cache.cache_buffer(new_checksum, new_value_buffer)
    buffer_cache.guarantee_buffer_info(new_checksum, "plain", sync_to_remote=False)
    return new_checksum


def integrate_kwargs(kwargs_checksums):

    result = {}
    for kwarg, kwarg_checksum in kwargs_checksums.items():
        kwarg_checksum = Checksum(kwarg_checksum)
        if not kwarg_checksum:
            continue
        buf = get_buffer(kwarg_checksum, remote=False)
        if buf is not None:
            kwarg_value = deserialize_sync(buf, kwarg_checksum, "mixed", True)
            result[kwarg] = kwarg_value
    result_buffer = serialize_sync(result, "mixed")
    result_checksum = Buffer(result_buffer).get_checksum()
    buffer_cache.cache_buffer(result_checksum, result_buffer)
    buffer_cache.guarantee_buffer_info(result_checksum, "mixed", sync_to_remote=False)
    return result_checksum


def pull_module(pinname, upstreams, manager):
    accessor = upstreams.get(pinname)
    checksum = None
    if accessor is not None:  # unconnected
        checksum = Checksum(accessor._checksum)
    if checksum:
        buffer = manager.resolve(checksum)
        if buffer is not None:
            mod_def = deserialize_sync(buffer, checksum, "plain", True)
            mod_rest = None
            try:
                mod_type = mod_def["type"]
                if mod_type == "compiled":
                    mod_lang = None
                    mod_rest = deepcopy(mod_def)
                    mod_rest.pop("type")
                    objects = mod_rest["objects"]
                    mod_code = {}
                    for objname in objects:
                        obj_code = objects[objname].pop("code", "")
                        mod_code[objname] = obj_code
                else:
                    mod_lang = mod_def["language"]
                    mod_code = mod_def["code"]
            except Exception:
                mod_type, mod_lang, mod_rest, mod_code = None, None, None, None
    else:
        mod_type, mod_lang, mod_rest, mod_code = None, None, None, None
    return mod_type, mod_lang, mod_rest, mod_code, checksum


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
    def __init__(self, tf, path, special):
        self.tf = tf
        self.path = path
        self.mount_ctx = None
        self.result_pinname = None
        self.special = special  # None, "compiled", "bash", "bashdocker"
        self.modules = {}
        self._pulling = False
        self._object_codes = {}
        self.kwargs_cells = {}
        self.pinname_to_cells = {}
        self.skip_pins = None

    def mount(self, skip_pins):
        from ..core.context import context
        from ..core.macro_mode import macro_mode_on
        from ..core.cell import (
            subcelltypes,
            extensions,
            cell as core_cell,
            cellclasses,
        )

        skip_pins = skip_pins.copy()
        self.skip_pins = skip_pins
        if self.special is not None:
            skip_pins += ["code", "input_name", "result_name"]
            if self.special == "bash":
                skip_pins.append("pins_")
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
        assert not len(self.modules)  # cannot re-mount
        with macro_mode_on():
            self.mount_ctx = context(toplevel=True)
            self.pinname_to_cells = {}
            pinname_to_cells = self.pinname_to_cells
            for pinname, pin in tf._pins.items():
                if pinname in skip_pins:
                    continue
                celltype = pin.celltype
                subcelltype = pin.subcelltype
                if pinname == "kwargs" and self.special == "compiled":
                    checksum = None
                    accessor = upstreams.get(pinname)
                    if accessor is not None:
                        checksum = accessor._checksum
                    kwargs_checksums = parse_kwargs(checksum)
                    self.kwargs_cells = set(kwargs_checksums.keys())
                    pinname_to_cells["kwargs"] = []
                    for kwargs_cell in self.kwargs_cells:
                        c = core_cell("mixed")
                        filename = os.path.join(self.path, kwargs_cell) + ".mixed"
                        cellname = "KWARGS_" + kwargs_cell
                        setattr(self.mount_ctx, cellname, c)
                        pinname_to_cells["kwargs"].append(cellname)
                        c.mount(filename, mode="rw", authority="cell", persistent=False)
                        kwargs_checksum = kwargs_checksums.get(kwargs_cell)
                        kwargs_checksum = Checksum(kwargs_checksum)
                        if kwargs_checksum:
                            c.set_checksum(kwargs_checksum)
                    continue
                if celltype is None:
                    pin_cells = manager.cell_from_pin(pin)
                    if isinstance(pin_cells, tuple):
                        pin_cells = [pin_cells]
                    if len(pin_cells) == 0:
                        celltype = "mixed"
                    else:
                        celltype = pin_cells[0][0].celltype
                        subcelltype = pin_cells[0][0]._subcelltype
                if subcelltype == "module":
                    mod_type, mod_lang, mod_rest, mod_code, mod_cs = pull_module(
                        pinname, upstreams, manager
                    )
                    if mod_type == "compiled":
                        print("Mounting compiled module")
                        mod_rest["target"] = "debug"
                        obj_rest = mod_rest["objects"]
                        pinname_to_cells[pinname] = []
                        singleton = pinname == "module" and list(mod_code.keys()) == [
                            "main"
                        ]
                        for objname in mod_code:
                            obj_code = mod_code[objname]
                            if not singleton:
                                obj_dir = os.path.join(self.path, pinname)
                                os.makedirs(obj_dir, exist_ok=True)
                            else:
                                obj_dir = self.path
                            lang = obj_rest[objname].get("language")
                            if lang is None:
                                msg = "Module object '{}.{}' has unknown language, mounting to .txt file"
                                print(msg.format(pinname, objname))
                                ext = ".txt"
                            else:
                                ext = "." + language_to_extension(lang, "txt")
                            obj_path = os.path.join(obj_dir, objname) + ext
                            c = core_cell("text")
                            c.mount(
                                obj_path, mode="rw", authority="cell", persistent=False
                            )
                            cellname = module_tag + pinname + "." + objname
                            setattr(self.mount_ctx, cellname, c)
                            c.set(obj_code)
                            self._object_codes[cellname] = obj_code
                            pinname_to_cells[pinname].append(cellname)
                            mod_cs = integrate_compiled_module(
                                mod_lang, mod_rest, self._object_codes
                            )
                        if mod_cs is not None:
                            buffer_cache.incref(mod_cs, persistent=True)
                        self.modules[pinname] = mod_type, mod_lang, mod_rest, mod_cs
                        continue
                    if mod_lang is None:
                        msg = "Module '{}' has unknown language, mounting to .txt file"
                        print(msg.format(pinname))
                        ext = ".txt"
                    else:
                        ext = "." + language_to_extension(mod_lang, "txt")
                    mod_code = analyze_mod_code(mod_code, pinname)
                    if mod_cs is not None:
                        buffer_cache.incref(mod_cs, persistent=True)
                    self.modules[pinname] = mod_type, mod_lang, mod_rest, mod_cs
                    c = core_cell("text")
                else:
                    if subcelltype is not None:
                        cellclass = subcelltypes[subcelltype]
                    else:
                        if celltype not in cellclasses:
                            raise NotImplementedError(celltype, cellclasses)
                        cellclass = cellclasses[celltype]
                    c = cellclass()
                    ext = extensions[cellclass]
                filename = os.path.join(self.path, pinname) + ext
                mode = "w" if pinname == self.result_pinname else "rw"
                c.mount(filename, mode=mode, authority="cell", persistent=False)
                setattr(self.mount_ctx, pinname, c)
                pinname_to_cells[pinname] = [pinname]
                if subcelltype == "module":
                    if mod_code is not None:
                        c.set(mod_code)
                else:
                    checksum = None
                    accessor = upstreams.get(pinname)
                    if accessor is not None:
                        checksum = Checksum(accessor._checksum)
                    if checksum:
                        c.set_checksum(checksum)
        for pinname, pin in tf._pins.items():
            if pinname in skip_pins:
                continue
            if pinname == self.result_pinname:
                continue
            for cellname in pinname_to_cells[pinname]:
                c = getattr(self.mount_ctx, cellname)
                c._set_observer(functools.partial(self._observe, cellname), False)

    def _observe(self, cellname: str, checksum):
        if self._pulling:
            return
        if cellname.startswith("KWARGS_"):
            cellname2 = cellname[len("KWARGS_") :]
            if cellname2 in self.kwargs_cells:
                self._transformer_update()
                return
        if cellname.startswith(module_tag):
            cellname2 = cellname[len(module_tag) :]
            pos = cellname2.index(".")
            module_name = cellname2[:pos]
            obj_name = cellname2[pos + 1 :]
            mod_type, mod_lang, mod_rest, old_mod_cs = self.modules[module_name]
            assert mod_type == "compiled"
            code = checksum_to_code(checksum)
            self._object_codes[cellname] = code
            new_checksum = integrate_compiled_module(
                mod_lang, mod_rest, self._object_codes
            )
            buffer_cache.incref(new_checksum, persistent=True)
            if old_mod_cs is not None:
                buffer_cache.decref(old_mod_cs)
            self.modules[module_name] = mod_type, mod_lang, mod_rest, new_checksum
        elif cellname in self.modules:
            code = checksum_to_code(checksum)
            mod_type, mod_lang, mod_rest, old_mod_cs = self.modules[cellname]
            new_value = {
                "language": mod_lang,
                "type": mod_type,
            }
            if code is not None:
                new_value["code"] = code
            new_value_buffer = serialize_sync(new_value, "plain")
            new_checksum = Buffer(new_value_buffer).get_checksum()
            buffer_cache.incref_buffer(new_checksum, new_value_buffer, persistent=True)
            if old_mod_cs is not None:
                buffer_cache.decref(old_mod_cs)
            self.modules[cellname] = mod_type, mod_lang, mod_rest, new_checksum
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
                old_mod_cs = None
                if pinname in self.skip_pins:
                    continue
                if pinname in self.modules:
                    mod_type, mod_lang, mod_rest, mod_code, mod_cs = pull_module(
                        pinname, upstreams, manager
                    )
                    if self.special == "compiled" and pinname == "module":
                        _, mod_lang_old, _, old_mod_cs = self.modules[pinname]
                        mod_type = "compiled"
                        mod_lang = mod_lang_old
                        if mod_code is None:
                            mod_code = {}
                        for objname in mod_code:
                            obj_code = mod_code[objname]
                            cellname = module_tag + pinname + "." + objname
                            c = getattr(self.mount_ctx, cellname, None)
                            if c is not None:
                                c.set(obj_code)
                                self._object_codes[cellname] = obj_code
                        if old_mod_cs is not None:
                            buffer_cache.decref(old_mod_cs)
                        if mod_cs is not None:
                            buffer_cache.incref(mod_cs, persistent=True)
                        self.modules[pinname] = mod_type, mod_lang, mod_rest, mod_cs
                        continue
                    mod_code = analyze_mod_code(mod_code, pinname)
                    if old_mod_cs is not None:
                        buffer_cache.decref(old_mod_cs)
                    if mod_cs is not None:
                        buffer_cache.incref(mod_cs, persistent=True)
                    self.modules[pinname] = mod_type, mod_lang, mod_rest, mod_cs
                    if mod_code is not None:
                        c = getattr(self.mount_ctx, pinname)
                        c.set(mod_code)
                else:
                    checksum = None
                    if accessor is not None:  # unconnected
                        checksum = Checksum(accessor._checksum)
                    if pinname == "kwargs" and self.special == "compiled":
                        kwargs_checksums = parse_kwargs(checksum)
                        for k, cs in kwargs_checksums.items():
                            if k not in self.kwargs_cells:
                                continue
                            kk = "KWARGS_" + k
                            c = getattr(self.mount_ctx, kk)
                            c.set_checksum(cs)
                    else:
                        c = getattr(self.mount_ctx, pinname)
                        c.set_checksum(checksum)
            self._pulling = False
            self._transformer_update()
        finally:
            self._pulling = False

    def destroy(self):
        try:
            self.mount_ctx.destroy()
            for _, _, _, checksum in self.modules.values():
                checksum = Checksum(checksum)
                if checksum:
                    buffer_cache.decref(checksum)
        finally:
            shutil.rmtree(self.path, ignore_errors=True)


class DebugMountManager:
    def __init__(self):
        self._mounts = {}

    def add_mount(self, tf, skip_pins=None, *, special=None, prefix=None):
        # print("ADD MOUNT", tf)
        if skip_pins is None:
            skip_pins = []
        if SEAMLESS_DEBUGGING_DIRECTORY is None:
            raise Exception("""SEAMLESS_DEBUGGING_DIRECTORY undefined.""")
        path = None
        if prefix is None:
            prefix = ""
        else:
            first_dir = os.path.join(SEAMLESS_DEBUGGING_DIRECTORY, "sandbox-" + prefix)
            if not os.path.exists(first_dir):
                path = first_dir
                os.makedirs(path)
            else:
                prefix += "-"
        if path is None:
            path = tempfile.mkdtemp(
                dir=SEAMLESS_DEBUGGING_DIRECTORY, prefix="sandbox-" + prefix
            )
        mount = DebugMount(tf, path, special=special)
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
        # print("REMOVE MOUNTS", hex(id(ctx)))
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

    def debug_result(self, transformer, checksum: Checksum):
        checksum = Checksum(checksum)
        mount = self._mounts[transformer]
        mount_ctx = mount.mount_ctx
        result = getattr(mount_ctx, mount.result_pinname)
        result.set_checksum(checksum)

    def has_debug_result(self, transformer) -> bool:
        if not self.is_mounted(transformer):
            return False
        mount = self._mounts[transformer]
        mount_ctx = mount.mount_ctx
        result = getattr(mount_ctx, mount.result_pinname)
        return bool(Checksum(result.checksum))

    async def run(self, transformer):
        mount = self._mounts[transformer]
        mount_ctx = mount.mount_ctx
        input_pins = {}
        celltypes = {}
        manager = transformer._get_manager()
        livegraph = manager.livegraph
        upstreams = livegraph.transformer_to_upstream[transformer]

        for pinname in transformer._pins:
            if pinname == "META":
                continue
            if pinname == mount.result_pinname:
                continue
            pin = transformer._pins[pinname]
            celltype, subcelltype = pin.celltype, pin.subcelltype
            if pinname in mount.skip_pins:
                accessor = upstreams.get(pinname)
                checksum = None
                if accessor is not None:  # unconnected
                    checksum = accessor._checksum
                if celltype is None:
                    wa = accessor.write_accessor
                    celltype, subcelltype = wa.celltype, wa.subcelltype
            else:
                if pinname in mount.modules:
                    _, _, _, checksum = mount.modules[pinname]
                elif pinname == "kwargs" and mount.special == "compiled":
                    kwargs_checksums = {}
                    for kwarg in mount.kwargs_cells:
                        cellname = "KWARGS_" + kwarg
                        c = getattr(mount_ctx, cellname)
                        kwargs_checksums[kwarg] = c._checksum
                    checksum = integrate_kwargs(kwargs_checksums)
                    celltype, subcelltype = "mixed", None
                else:
                    c = getattr(mount_ctx, pinname)
                    checksum = c._checksum
                if celltype is None:
                    celltype, subcelltype = c.celltype, c._subcelltype

            input_pins[pinname] = checksum
            celltypes[pinname] = celltype, subcelltype

            checksum = Checksum(checksum)
            if not checksum:
                ok = False
                break
        else:
            ok = True
        if not ok:
            self.debug_result(transformer, None)
            return
        result_cell = getattr(mount_ctx, mount.result_pinname)
        outputpin = mount.result_pinname, result_cell.celltype, result_cell._subcelltype
        if result_cell._hash_pattern is not None:
            outputpin += (result_cell._hash_pattern,)
        manager = transformer._get_manager()
        transformation_cache = manager.cachemanager.transformation_cache
        try:
            await transformation_cache.update_transformer(
                transformer, celltypes, input_pins, outputpin
            )
        except Exception:
            pass

    def destroy(self):
        for tf in list(self._mounts.keys()):
            self.remove_mount(self._mounts[tf])


debugmountmanager = DebugMountManager()
from seamless.checksum.buffer_cache import buffer_cache
import atexit

atexit.register(debugmountmanager.destroy)
