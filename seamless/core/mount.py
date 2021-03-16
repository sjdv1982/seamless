"""
_init() is invoked at startup:
 If authority is "file" or "file-strict":
  This may invoke _read(), but only if the file exists
   (if cell is non-empty and is different, a warning is printed)
   ("file-strict": the file must exist)
  If not, this may invoke _write(), but only if the cell is non-empty
 If authority is "cell":
   This may invoke _write(), but only if the cell is non-empty
     (if the file exists and is different, a warning is printed)
   If not, this may invoke _read(), but only if the file exists
Periodically, conditional_read() and conditional_write() are invoked,
 that check if a read/write is necessary, and if so, invoke _read()/_write()
"""
from weakref import WeakValueDictionary, WeakKeyDictionary, WeakSet, ref
import threading
from threading import Thread, RLock, Event
from collections import deque, OrderedDict
from speg.peg import ParseError
import sys, os
import time
import traceback
import copy
from contextlib import contextmanager
import json
import itertools
import functools

from ..get_hash import get_hash

import sys
def log(*args, **kwargs):
    print(*args, **kwargs, file=sys.stderr)

def multicaps(s):
    if s is None:
        return False
    if isinstance(s, tuple):
        for ss in s:
            if multicaps(ss):
                return True
        return False
    if not isinstance(s, str):
        raise TypeError(type(s))
    for n in range(len(s)-1):
        if s[n].isupper() and s[n+1].isupper():
            return True
    return False

empty_checksums = {get_hash(json.dumps(v)+"\n",hex=True) for v in ("", {}, [])}

def adjust_buffer(file_buffer, celltype):
    if celltype not in text_types:
        return file_buffer
    return file_buffer.rstrip(b'\n') + b'\n'

def is_dummy_mount(mount):
    if mount is None:
        return True
    assert isinstance(mount, dict), mount
    if list(mount.keys()) == ["extension"]:
        return True
    return False

def lockmethod(func):
    def wrapper(self, *args, **kwargs):
        with self.lock:
            return func(self, *args, **kwargs)
    functools.update_wrapper(wrapper, func)
    return wrapper

def lockfunc(func):
    def wrapper(*args, **kwargs):
        with mountmanager.lock:
            return func(*args, **kwargs)
    functools.update_wrapper(wrapper, func)
    return wrapper

class MountItem:
    last_exc = None
    parent = None
    _destroyed = False
    _initialized = False
    def __init__(self, parent, cell, path, mode, authority, persistent, *,
      dummy=False, as_directory=False, **kwargs
    ):
        if parent is not None:
            self.parent = ref(parent)
        self.path = path
        self.cell = ref(cell)
        self.dummy = dummy
        assert mode in ("r", "w", "rw"), mode #read from file, write to file, or both
        self.mode = mode
        assert persistent in (True, False, None)
        assert authority in ("cell", "file", "file-strict"), authority
        if authority == "file-strict":
            assert persistent
            assert "r" in self.mode, (authority, mode)
        elif authority == "file":
            if "r" not in self.mode:
                authority = "cell"
        self.authority = authority
        if as_directory:
            assert cell.celltype == "plain", cell.celltype  # TODO: as_directory mounting of mixed cells
        self.as_directory = as_directory
        self.kwargs = kwargs
        self.last_checksum = None
        self.last_mtime = None
        self.persistent = persistent
        self.cell_checksum = None
        self.cell_buffer = None

    def init(self):
        assert threading.current_thread() == threading.main_thread()
        #print("INIT", self.cell(), self.cell().has_authority())
        if self._destroyed:
            return
        assert self.parent is not None
        cell = self.cell()
        if cell is None:
            return
        if cell._destroyed:
            return
        if "r" in self.mode:
            assert cell.has_authority(), cell # mount read mode only for authoritative cells
        exists = self._exists()
        cell_checksum = cell._checksum
        cell_empty = (cell_checksum is None)
        if not cell_empty:
            if cell_checksum in empty_checksums:
                cell_empty = True
        from_cache = False
        cache_cell_checksum, cache_cell_buffer = self._from_cache()
        if cache_cell_checksum is not None:
            if cell_empty or cache_cell_checksum == cell_checksum:
                from_cache = True
        from_garbage = (mountmanager.garbage.pop(self.path, None) is not None)
        if not from_cache:
            from_garbage = False
        if cell_empty:
            cell_checksum, cell_buffer = cache_cell_checksum, cache_cell_buffer
            cell_empty = (cell_checksum is None)
            if not cell_empty:
                if cell_checksum in empty_checksums:
                    cell_empty = True
        else:
            if from_cache:
                cell_buffer = cache_cell_buffer
            else:
                cell_buffer = buffer_cache.get_buffer(cell_checksum)
                if cell_buffer is None:
                    cell_checksum = None
                    cell_empty = True
        self.cell_buffer = cell_buffer
        self.cell_checksum = cell_checksum
        if self.authority in ("file", "file-strict"):
            if exists:
                with self.lock:
                    if self._destroyed:
                        return
                    file_buffer0 = self._read()
                    file_buffer = adjust_buffer(file_buffer0, cell._celltype)
                    update_file = True
                    file_checksum = None
                    if not cell_empty:
                        file_checksum = calculate_checksum(file_buffer)
                        if file_checksum == cell_checksum:
                            update_file = False
                        else:
                            if cell_checksum is not None:
                                print(cell_checksum.hex())
                            print("Warning: File path '%s' has a different value, overwriting cell" % self.path) #TODO: log warning
                    self._after_read(file_checksum)
                if update_file:
                    self.set(file_buffer, checksum=file_checksum)
            elif self.authority == "file-strict":
                raise Exception("File path '%s' does not exist, but authority is 'file-strict'" % self.path)
            else:
                if "w" in self.mode and not cell_empty:
                    with self.lock:
                        self._write(cell_buffer)
                        self._after_write(cell_checksum)
        else: #self.authority == "cell"
            if not cell_empty :
                if not from_garbage or not exists:
                    if "w" in self.mode:
                        with self.lock:
                            self._write(cell_buffer)
                            self._after_write(cell_checksum)
                else:
                    self.last_checksum = cell_checksum
            elif exists:
                with self.lock:
                    if self._destroyed:
                        return
                    file_buffer0 = self._read()
                    file_buffer = adjust_buffer(file_buffer0, cell._celltype)
                    update_file = True
                    file_checksum = None
                    self._after_read(file_checksum)
                if update_file and "r" in self.mode:
                    self.set(file_buffer, checksum=file_checksum)

        self._initialized = True

    def set(self, file_buffer, checksum):
        if self._destroyed:
            return
        cell = self.cell()
        if cell is None:
            return
        if cell._celltype == "plain":
            if "w" in self.mode:
                try:
                    c = cson2json(file_buffer.decode())
                    j1 = (json.dumps(c, sort_keys=True, indent=2) + "\n").encode()
                    old_checksum = checksum
                    checksum = calculate_checksum(j1)
                    file_buffer = j1
                    if checksum != old_checksum:
                        if checksum is not None and len(adjust_buffer(file_buffer, "plain")):
                            self._write(file_buffer)
                except (ValueError, ParseError):
                    pass
        cell.set_buffer(file_buffer, checksum)

    @property
    def lock(self):
        assert self.parent is not None
        return self.parent().lock

    def _from_cache(self):
        cache = mountmanager.cached_checksums.pop(self.path, (None, None) )
        cached_time, cached_checksum = cache
        buffer = buffer_cache.get_buffer(cached_checksum)
        if buffer is not None:
            self.last_mtime = cached_time
        return cached_checksum, buffer

    def _read_as_directory(self):
        result = {}
        try:
            def scan(path, subresult):
                with os.scandir(path) as it:
                    for entry in it:
                        name = entry.name
                        if entry.is_file():
                            filemode = "r" # TODO: binary file for mixed cells => try to decode
                            with open(entry.path, filemode) as f:
                                data = f.read().strip("\n")
                            subresult[name] = data
                        elif entry.is_dir():
                            subsubresult = {}
                            scan(entry.path, subsubresult)
                            if len(subsubresult):
                                subresult[name] = subsubresult
            scan(self.path, result)
            data = json.dumps(result, sort_keys=True, indent=2)
            buffer = data.encode()
            return buffer
        except RuntimeError:
            pass


    def _read(self):
        if self._destroyed:
            return
        #print("read", self.cell())
        if self.as_directory:
            return self._read_as_directory()
        binary = self.kwargs["binary"]
        encoding = self.kwargs.get("encoding")
        filemode = "rb" if binary else "r"
        with open(self.path, filemode, encoding=encoding) as f:
            result = f.read()
            if not binary:
                result = result.encode()
        return result

    def _write_as_directory(self, file_buffer, with_none):
        os.makedirs(self.path, exist_ok=True)
        if with_none and file_buffer is None:
            return
        data = json.loads(file_buffer)
        if not isinstance(data, dict):
            return
        def write(subdata, subpath):
            os.makedirs(os.path.join(*subpath), exist_ok=True)
            for k,v in subdata.items():
                subpath2 = subpath + (k,)
                if isinstance(v, dict):
                    write(v, subpath2)
                else:
                    vv = str(v)
                    filename = os.path.join(*subpath2)
                    with open(filename, "w") as f:
                        f.write(vv + "\n")
        write( data, (self.path,) )

    def _write(self, file_buffer, with_none=False):
        if self._destroyed:
            return
        assert "w" in self.mode
        if self.as_directory:
            return self._write_as_directory(file_buffer, with_none)
        binary = self.kwargs["binary"]
        encoding = self.kwargs.get("encoding")
        filemode = "wb" if binary else "w"
        if file_buffer is None:
            if not with_none:
                if os.path.exists(self.path):
                    os.unlink(self.path)
                return
            file_buffer = b"" if binary else ""
        else:
            assert isinstance(file_buffer, bytes), type(file_buffer)
            if not binary:
                file_buffer = file_buffer.decode()
        with open(self.path, filemode, encoding=encoding) as f:
            f.write(file_buffer)

    def _exists(self):
        return os.path.exists(self.path)

    def _after_write(self, checksum):
        self.last_checksum = checksum
        try:
            mtime = self._get_mtime()
            self.last_mtime = mtime
        except Exception:
            pass

    def conditional_write(self, checksum, buffer, with_none=False):
        if not self._initialized:
            return
        if self._destroyed:
            return
        if not "w" in self.mode:
            return
        cell = self.cell()
        if cell is None:
            return
        if checksum is None:
            if not with_none:
                return
        self.cell_checksum = checksum
        self.cell_buffer = buffer
        if checksum is None or self.last_checksum != checksum:
            with self.lock:
                self._write(buffer, with_none=with_none)
                self._after_write(checksum)

    def _after_read(self, checksum, *, mtime=None):
        self.last_checksum = checksum
        if mtime is None:
            mtime = self._get_mtime()
        if self.last_mtime is None or mtime > self.last_mtime:
            self.last_mtime = mtime

    def _get_mtime(self):
        if self.as_directory:
            if not os.path.exists(self.path) or not os.path.isdir(self.path):
                return None
            stat = os.stat(self.path)
            mtime = stat.st_mtime
            try:
                def scan(path):
                    nonlocal mtime
                    with os.scandir(path) as it:
                        for entry in it:
                            if entry.is_file() or entry.is_dir():
                                f_mtime = entry.stat().st_mtime
                                #print(entry.path, f_mtime)
                                if mtime is None or f_mtime > mtime:
                                    mtime = f_mtime
                            if entry.is_dir():
                                scan(entry.path)
                scan(self.path)
            except RuntimeError:
                pass
            return mtime
        else:
            stat = os.stat(self.path)
            mtime = stat.st_mtime
            return mtime

    def conditional_read(self):
        if not self._initialized:
            return
        if self._destroyed:
            return
        cell = self.cell()
        if cell is None:
            return
        if not self._exists():
            return
        with self.lock:
            if self._destroyed:
                return
            mtime = self._get_mtime()
            file_checksum = None
            if self.last_mtime is None or mtime > self.last_mtime:
                file_buffer0 = self._read()
                file_buffer = adjust_buffer(file_buffer0, cell._celltype)
                file_checksum = calculate_checksum(file_buffer)
                self._after_read(file_checksum, mtime=mtime)
        cell_checksum = self.cell_checksum
        if file_checksum is not None and file_checksum != cell_checksum:
            if "r" in self.mode:
                self.set(file_buffer, checksum=file_checksum)
            else:
                print("Warning: write-only file %s (%s) has changed on disk, overruling" % (self.path, self.cell()))
                cell_buffer = self.cell_buffer
                with self.lock:
                    self._write(cell_buffer)
                    self._after_write(cell_checksum)

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        if self.dummy:
            return
        now = time.time()
        if self.cell_checksum is not None:
            mountmanager.cached_checksums[self.path] = (now, self.cell_checksum)
        if self.persistent == False:
            mountmanager.garbage[self.path] = (now, False)

    def __del__(self):
        if self.dummy:
            return
        if self._destroyed:
            return
        self._destroyed = True
        log("undestroyed mount path %s" % self.path)
        #self.destroy()

class LinkItem:
    _destroyed = False
    linked_path = None
    def __init__(self, unilink, path, persistent):
        self.unilink = ref(unilink)
        self.path = path
        self.persistent = persistent

    def init(self):
        from .context import Context
        if self._destroyed:
            return
        linked = self.get_linked()
        is_dir = (isinstance(linked, Context))
        if is_dummy_mount(linked._mount):
            return
        linked_path = linked._mount["path"]
        os.symlink(linked_path, self.path, is_dir)
        self.linked_path = linked_path

    def get_linked(self):
        if self._destroyed:
            return
        unilink = self.unilink()
        if unilink is None:
            return
        linked = unilink.get_linked()
        return linked

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        if self.persistent == False:
            filepath = self.path
            mountmanager.garbage[filepath] = (time.time(), True)

    def __del__(self):
        if self._destroyed:
            return
        self._destroyed = True
        log("undestroyed unilink path %s" % self.path)

class MountManager:
    GARBAGE_DELAY = 20
    _running = False
    _last_run = None
    _stop = False
    _mounting = False
    thread = None
    def __init__(self, latency):
        self.latency = latency
        self.mounts = {}
        self.contexts = WeakSet()
        self.lock = RLock()
        self.cell_updates = deque()
        self._tick = Event()
        self.paths = WeakKeyDictionary()
        self.cached_checksums = {} # key: file path; value: (deletion time, checksum)
        self.garbage = {} # non-persistent mounts to delete. key = path, value = (deletion time, is_link)
        self.garbage_dirs = {} # non-persistent directories to delete. key = path, value = (deletion time, persistent).
                               # persistent may be None, in which case the directory is not deleted.


    @property
    def last_run(self):
        return self._last_run

    @lockmethod
    def add_mount(self, cell, path, mode, authority, persistent, **kwargs):
        root = cell._root()
        if root not in self.paths:
            paths = set()
            self.paths[root] = paths
        else:
            paths = self.paths[root]
        assert path not in paths, path
        #print("add mount", path, cell)
        paths.add(path)
        item = MountItem(self, cell, path, mode, authority, persistent, **kwargs)
        self.mounts[cell] = item
        return item

    @lockmethod
    def add_link(self, unilink, path, persistent):
        paths = self.paths[unilink._root()]
        assert path not in paths, path
        #print("add unilink", path, unilink)
        paths.add(path)
        item = LinkItem(unilink, path, persistent)
        self.mounts[unilink] = item
        return item

    @lockmethod
    def unmount(self, cell_or_unilink, from_del=False):
        assert hasattr(cell_or_unilink, "_mount"), cell_or_unilink
        assert not is_dummy_mount(cell_or_unilink._mount), cell_or_unilink
        root = cell_or_unilink._root()
        if from_del and (cell_or_unilink not in self.mounts or root not in self.paths):
            return
        if cell_or_unilink not in self.mounts or root not in self.paths:
            # KLUDGE
            return
        mount_item = self.mounts.pop(cell_or_unilink)
        if not mount_item._destroyed:
            if root in self.paths:
                paths = self.paths[root]
                path = cell_or_unilink._mount["path"]
                paths.discard(path)
            mount_item.destroy()

    @lockmethod
    def unmount_context(self, context, from_del=False, toplevel=False):
        if context in self.contexts:
            self.contexts.remove(context)
        elif not from_del and not toplevel:
            return
        mount = context._mount
        if toplevel:
            self.paths.pop(context, None)
            if mount is None:
                return
        #print("unmount context", context)
        assert not is_dummy_mount(mount), context
        try:
            paths = self.paths[context._root()]
        except KeyError:
            if not from_del:
                return
            paths = set()
        try:
            paths.remove(mount["path"])
        except KeyError:
            pass
        if mount["persistent"] != True:
            dirpath = mount["path"]
            mountmanager.garbage_dirs[dirpath] = time.time(), mount["persistent"]

    @lockmethod
    def add_context(self, context, as_parent):
        path = context._mount["path"]
        #print("add context", path, context, as_parent, context._mount["persistent"])
        paths = self.paths[context._root()]
        if not as_parent:
            if context not in self.contexts:
                assert path not in paths, path
                paths.add(path)
                self.contexts.add(context)
        else:
            if path in paths:
                assert context in self.contexts, (path, context)

    def _check_context(self, context, as_parent):
        mount = context._mount
        assert not is_dummy_mount(mount), context
        in_garbage = self.garbage_dirs.get(mount["path"], None)
        dirpath = mount["path"]
        persistent, authority = mount["persistent"], mount["authority"]
        if os.path.exists(dirpath):
            if authority == "cell" and not as_parent and in_garbage is None:
                print("Warning: Directory path '%s' already exists" % dirpath) #TODO: log warning
        else:
            if authority == "file-strict":
                raise Exception("Directory path '%s' does not exist, but authority is 'file-strict'" % dirpath)
            os.mkdir(dirpath)
        if in_garbage is None and persistent != True:
            self.garbage_dirs[dirpath] = time.time(), mount["persistent"]


    @lockmethod
    def add_cell_update(self, cell, checksum, buffer):
        if self._mounting:
            return
        root = cell._root()
        if root is not None and root not in mountmanager.paths:
            return
        if cell not in self.mounts:
            # KLUDGE
            return
        #assert cell in self.mounts, (cell, hex(id(cell)))
        self.cell_updates.append((cell, checksum, buffer))

    def run_once(self):
        cell_updates = {cell: (checksum, buffer) \
            for cell, checksum, buffer in self.cell_updates}
        self.cell_updates.clear()
        for cell, mount_item in list(self.mounts.items()):
            if isinstance(cell, UniLink):
                continue
            if cell in cell_updates:
                continue
            try:
                mount_item.conditional_read()
            except Exception:
                exc = traceback.format_exc()
                if exc != mount_item.last_exc:
                    print(exc)
                    mount_item.last_exc = exc
        for cell, checksum_buffer in cell_updates.items():
            checksum, buffer = checksum_buffer
            mount_item = self.mounts.get(cell)
            if mount_item is None: #cell was deleted
                continue
            try:
                mount_item.conditional_write(checksum, buffer, with_none=False)
            except Exception:
                exc = traceback.format_exc()
                if exc != mount_item.last_exc:
                    print(exc)
                    mount_item.last_exc = exc
        now = time.time()
        to_destroy = []
        for filepath, value in self.garbage.items():
            mod_time, _ = value
            if now > mod_time + self.GARBAGE_DELAY:
                to_destroy.append(filepath)
        for filepath in to_destroy:
            _, is_link = self.garbage.pop(filepath)
            self._destroy_garbage(filepath, is_link)
        to_destroy = []
        for dirpath, value in self.garbage_dirs.items():
            mod_time, persistent = value
            if now > mod_time + self.GARBAGE_DELAY:
                to_destroy.append((dirpath, persistent))
        for dirpath, persistent in to_destroy:
            # if persistent is None, directory stays in garbage, for a cache hit
            if persistent == False:
                self.garbage_dirs.pop(dirpath)
                self._destroy_garbage_dir(dirpath)

        self._tick.set()
        self._last_run = time.time()

    def run(self):
        try:
            self._running = True
            while not self._stop:
                t = time.time()
                try:
                    self.run_once()
                except Exception:
                    self._tick.set()
                    import traceback
                    traceback.print_exc()
                while time.time() - t < self.latency:
                    time.sleep(0.05)
        finally:
            self._running = False

    def start(self):
        if self._running:
            return
        self._stop = False
        t = self.thread = Thread(target=self.run)
        t.setDaemon(True)
        t.start()

    def stop(self, wait=False, waiting_loop_period=0.01):
        self._stop = True
        if wait:
            while self._running:
                time.sleep(waiting_loop_period)

    def tick(self):
        """Waits until one iteration of the run() loop has finished"""
        if self._running:
            self._tick.clear()
            self._tick.wait()


    def _destroy_garbage(self, filepath, is_link):
        if is_link:
            unbroken_link = os.path.islink(filepath)
            broken_link = (os.path.lexists(filepath) and not os.path.exists(filepath))
            if unbroken_link or broken_link:
                os.unlink(filepath)
        else:
            if os.path.exists(filepath):
                os.unlink(filepath)


    def _destroy_garbage_dir(self, dirpath):
        try:
            #print("rmdir", dirpath)
            os.rmdir(dirpath)
        except Exception:
            print("Error: cannot remove directory %s" % dirpath)


    def clear(self):
        for cell in list(self.mounts.keys()):
            assert isinstance(cell, Cell), cell
            self.unmount(cell)
        for context in sorted(self.contexts,key=lambda l:-len(l.path)):
            self.unmount_context(context)

        self.cached_checksums.clear()
        for filepath in list(self.garbage.keys()):
            _, is_link = self.garbage[filepath]
            self._destroy_garbage(filepath, is_link)
        self.garbage.clear()

        dirpaths = sorted(
            self.garbage_dirs.keys(),
            key=lambda k:-len(k.split(os.sep))
        )
        for dirpath in dirpaths:
            _, persistent = self.garbage_dirs[dirpath]
            if persistent == False:
                self._destroy_garbage_dir(dirpath)
        self.garbage_dirs.clear()

        for root in self.paths:
            print("Uncleared root context:", root)
        self.paths.clear()
        for cell in self.mounts:
            print("Uncleared mounted cell:", cell)
        self.mounts.clear()

@lockfunc
def scan(ctx_or_cell):
    """Scans a cell or a context and its children for _mount attributes, and mounts them
    """
    from .context import Context
    from .unbound_context import UnboundContext
    from .cell import Cell
    from . import Worker, Macro
    assert not mountmanager._mounting

    if isinstance(ctx_or_cell, UnboundContext):
        raise TypeError(ctx_or_cell)

    root = ctx_or_cell._root()
    if root is not None and root not in mountmanager.paths:
        mountmanager.paths[root] = set()

    contexts = set()
    cells = set()
    links = set()
    mounts = mountmanager.mounts.copy()
    if sys.exc_info()[0] is not None:
        return #No mounting if there is an exception
    def find_mount(c, as_parent=False, child=None):
        if as_parent:
            assert child is not None
        #elif multicaps(c.path):
        #    return
        if c in mounts:
            result = mounts[c]
        elif not is_dummy_mount(c._mount):
            result = c._mount.copy()
            if result["path"] is None:
                parent = c._context
                assert parent is not None, c
                parent = parent()
                parent_result = find_mount(parent, as_parent=True,child=c)
                if parent_result is None:
                    raise Exception("No path provided for mount of %s, but no ancestor context is mounted" % c)
                result["path"] = parent_result["path"]
                result["autopath"] = True
        elif isinstance(c, Context) and c._toplevel:
            result = None
        else:
            if isinstance(c, Context) and c._macro is not None and c._context is None:
                parent = c._macro._context
            else:
                parent = c._context
                assert parent is not None, c
            parent = parent()
            result = None
            cc = c
            if isinstance(c, UniLink):
                cc = c.get_linked()
            if isinstance(cc, (Context, Cell)):
                result = find_mount(parent, as_parent=True,child=c)
            elif isinstance(cc, Macro):
                result = find_mount(parent, as_parent=False, child=cc.ctx)
        if not as_parent:
            mounts[c] = result
        if as_parent and result is not None:
            result = copy.deepcopy(result)
            if result["persistent"] is None:
                result["persistent"] = False
            result["autopath"] = True
            if isinstance(child, Context) and child._context is None and child._macro is not None:
                result["path"] += "/" + child._macro.name
            else:
                result["path"] += "/" + child.name
            if isinstance(child, UniLink):
                child = child.get_linked()
            if isinstance(child, Cell) and is_dummy_mount(child._mount):
                if child._structured_cell:
                    raise Exception("Structured cells cannot be mounted: %s" % child)
                else:
                    livegraph = child._get_manager().livegraph
                    if child._get_macro() is not None or not child.has_authority():
                        if result["mode"] == "r":
                            return None
                        result["mode"] = "w"
            extension = None
            if child._mount is not None:
                extension = child._mount.get("extension")
            if extension is not None:
                extension = "." + extension
            else:
                extension = get_extension(child)
            result["path"] += extension
        return result

    def enumerate_context(cctx):
        contexts.add(cctx)
        for child in cctx._children.values():
            if isinstance(child, Cell):
                if child.name not in cctx._auto:
                    cells.add(child)
            elif isinstance(child, Context):
                enumerate_context(child)
            elif isinstance(child, Macro):
                if child._gen_context is not None:
                    enumerate_context(child._gen_context)
    if isinstance(ctx_or_cell, Context):
        enumerate_context(ctx_or_cell)
    else:
        cells.add(ctx_or_cell)

    for context in contexts:
        find_mount(context)
    for cell in cells:
        find_mount(cell)

    done_contexts = set()
    contexts_to_mount = {}
    def mount_context_delayed(context, as_parent=False):
        if not context in mounts or mounts[context] is None:
            return
        if context in done_contexts:
            if not as_parent:
                contexts_to_mount[context] = False
            return
        parent = context._context
        if parent is not None:
            parent = parent()
            mount_context_delayed(parent, as_parent=True)
        object.__setattr__(context, "_mount", mounts[context]) #not in macro mode
        contexts_to_mount[context] = as_parent
        done_contexts.add(context)

    for context in contexts:
        mount_context_delayed(context)

    def propagate_persistency(c, persistent=False):
        m = c._mount
        if is_dummy_mount(m):
            return
        if persistent:
            m["persistent"] = True
        elif m["persistent"] == True and m.get("autopath"):
            persistent = True
        if isinstance(c, Context):
            if c._toplevel:
                return
        parent = c._context
        if isinstance(c, Context) and c._context is None and c._macro is not None:
            parent = c._macro._context
        assert parent is not None, c
        parent = parent()
        propagate_persistency(parent, persistent)
    for child in itertools.chain(contexts, cells):
        if not is_dummy_mount(child._mount):
            propagate_persistency(child)

    mount_cells = []
    for cell in cells:
        mount = mounts.get(cell)
        if isinstance(mount, dict) and not is_dummy_mount(mount):
            path = mount["path"]
            if cell._mount_kwargs is None:
                print("Warning: Unable to mount file path '%s': cannot mount this type of cell (%s)" % (path, type(cell).__name__))
                continue
            mount.update(cell._mount_kwargs)
            object.__setattr__(cell, "_mount", mount) #not in macro mode
            mount_cells.append(cell)

    mount_links = []
    for unilink in links:
        if unilink in mounts and not is_dummy_mount(mounts[unilink]):
            mount = mounts[unilink]
            path = mount["path"]
            object.__setattr__(unilink, "_mount", mount) #not in macro mode
            mount_links.append(unilink)

    ctx_to_mount = sorted(contexts_to_mount, key=lambda l:len(l.path))
    for ctx in ctx_to_mount:
        as_parent = contexts_to_mount[ctx]
        mountmanager._check_context(ctx, as_parent)
        mountmanager.add_context(ctx, as_parent)

    mount_items = []
    for cell in mount_cells:
        mount_item = mountmanager.add_mount(cell, **cell._mount)
        mount_items.append(mount_item)
    for mount_item in mount_items:
        mount_item.init()
    for unilink in mount_links:
        mount = unilink._mount
        mountmanager.add_link(unilink, mount["path"], mount["persistent"])


mountmanager = MountManager(0.2) #TODO: latency in config file

def get_extension(c):
    from .cell import extensions
    for k,v in extensions.items():
        if type(c) == k:
            return v
    for k,v in extensions.items():
        if isinstance(c, k):
            return v
    return ""

from .unilink import UniLink
from .cell import Cell
from .protocol.cson import cson2json
from .protocol.calculate_checksum import calculate_checksum_sync as calculate_checksum
from .cell import text_types
from .cache.buffer_cache import buffer_cache