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

NOTE: resolve_register returns immediately if there has been an exception raised
"""
from weakref import WeakValueDictionary, WeakKeyDictionary, WeakSet, ref
import threading
from threading import Thread, RLock, Event
from collections import deque, OrderedDict
import sys, os
import time
import traceback
import copy
from contextlib import contextmanager
import json
import itertools
import functools

from ..get_hash import get_hash

empty_checksums = {get_hash(json.dumps(v)+"\n",hex=True) for v in ("", {}, [])}

text_types = (
    "text", "python", "ipython", "cson", "yaml",
    "str", "int", "float", "bool",
)

def adjust_buffer(file_buffer, celltype):
    if file_buffer not in text_types:
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
    def __init__(self, parent, cell, path, mode, authority, persistent, *,
      dummy=False, **kwargs
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
        elif authority in ("file", "file-strict"):
            assert "r" in self.mode, (authority, mode)
        self.authority = authority
        self.kwargs = kwargs
        self.last_checksum = None
        self.last_time = None
        self.last_mtime = None
        self.persistent = persistent
        self.cell_checksum = None
        self.cell_buffer = None

    def init(self):
        assert threading.current_thread() == threading.main_thread()
        if self._destroyed:
            return
        assert self.parent is not None
        cell = self.cell()
        if cell is None:
            return
        exists = self._exists()
        cell_buffer, cell_checksum = cell.buffer_and_checksum
        self.cell_buffer = cell_buffer
        self.cell_checksum = cell_checksum
        cell_empty = (cell_checksum is None)
        if not cell_empty:
            if cell_checksum in empty_checksums:
                cell_empty = True
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
                            print("Warning: File path '%s' has a different value, overwriting cell" % self.path) #TODO: log warning
                    self._after_read(file_checksum)
                if update_file:
                    self.set(file_buffer, checksum=file_checksum)
            elif self.authority == "file-strict":
                raise Exception("File path '%s' does not exist, but authority is 'file-strict'" % self.path)
            else:
                if "w" in self.mode and not cell_empty:
                    with self.lock:
                        if self._destroyed:
                            return
                        self._write(cell_buffer)
                        self._after_write(cell_checksum)
        else: #self.authority == "cell"
            if not cell_empty:
                if "w" in self.mode:
                    with self.lock:
                        if self._destroyed:
                            return
                        self._write(cell_buffer)
                        self._after_write(cell_checksum)
 
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
                        self._write(file_buffer)
                except ValueError:  
                    pass
        cell.set_buffer(file_buffer, checksum)

    @property
    def lock(self):
        assert self.parent is not None
        return self.parent().lock

    def _read(self):
        #print("read", self.cell())
        binary = self.kwargs["binary"]
        encoding = self.kwargs.get("encoding")
        filemode = "rb" if binary else "r"
        with open(self.path.replace("/", os.sep), filemode, encoding=encoding) as f:
            result = f.read()
            if not binary:
                result = result.encode()
        return result

    def _write(self, file_buffer, with_none=False):
        assert "w" in self.mode
        binary = self.kwargs["binary"]
        encoding = self.kwargs.get("encoding")
        filemode = "wb" if binary else "w"
        filepath = self.path.replace("/", os.sep)
        if file_buffer is None:
            if not with_none:
                if os.path.exists(filepath):
                    os.unlink(filepath)
                return
            file_buffer = b"" if binary else ""
        else:
            assert isinstance(file_buffer, bytes), type(file_buffer)
            if not binary:
                file_buffer = file_buffer.decode()
        with open(filepath, filemode, encoding=encoding) as f:
            f.write(file_buffer)

    def _exists(self):
        return os.path.exists(self.path.replace("/", os.sep))


    def _after_write(self, checksum):
        self.last_checksum = checksum
        self.last_time = time.time()
        try:
            stat = os.stat(self.path)
            self.last_mtime = stat.st_mtime
        except Exception:
            pass

    def conditional_write(self, checksum, buffer, with_none=False):        
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
                if self._destroyed:
                    return
                self._write(buffer, with_none=with_none)
                self._after_write(checksum)

    def _after_read(self, checksum, *, mtime=None):
        self.last_checksum = checksum
        if mtime is None:
            stat = os.stat(self.path)
            mtime = stat.st_mtime
        self.last_mtime = mtime

    def conditional_read(self):
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
            stat = os.stat(self.path)
            mtime = stat.st_mtime
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
                    if self._destroyed:
                        return
                    self._write(cell_buffer)
                    self._after_write(cell_checksum)

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        if self.dummy:
            return
        if self.persistent == False and os.path.exists(self.path):
            #print("remove", self.path)
            os.unlink(self.path)

    def __del__(self):
        if self.dummy:
            return
        if self._destroyed:
            return
        self._destroyed = True
        print("undestroyed mount path %s" % self.path)
        #self.destroy()

class LinkItem:
    _destroyed = False
    linked_path = None
    def __init__(self, link, path, persistent):
        self.link = ref(link)
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
        link = self.link()
        if link is None:
            return
        linked = link.get_linked()
        return linked

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        if self.persistent == False:
            filepath = self.path
            unbroken_link = os.path.islink(filepath)
            broken_link = (os.path.lexists(filepath) and not os.path.exists(filepath))
            if unbroken_link or broken_link:
                os.unlink(filepath)

    def __del__(self):
        if self._destroyed:
            return
        self._destroyed = True
        print("undestroyed link path %s" % self.path)


def build_paths(path_context, top_paths, remove):
    path_mounts, path_contexts, path_paths = {}, set(), {}
    if path_context is None:
        return path_mounts, path_contexts, path_paths
    for ctx in list(mountmanager.contexts):
        assert not is_dummy_mount(ctx._mount), ctx
        path = ctx._mount["path"]
        if ctx._part_of(path_context):
            path_paths[path] = ctx
            path_contexts.add(ctx)
            if remove:
                top_paths.remove(path)
                mountmanager.contexts.remove(ctx)
    for cell, mountitem in mountmanager.mounts.items():        
        assert not is_dummy_mount(cell._mount), cell
        path = cell._mount["path"]
        if cell._context()._part_of(path_context):
            path_mounts[cell] = mountitem
            path_paths[path] = cell
            if remove:
                top_paths.remove(path)
    return path_mounts, path_contexts, path_paths

def join(items, contexts_to_mount, new, old):
    from .context import Context
    from .cell import Cell
    mounts = mountmanager.mounts
    contexts = mountmanager.contexts
    new_mounts, new_contexts, new_paths = new
    old_mounts, old_contexts, old_paths = old

    for ctx in contexts_to_mount:
        path = ctx._mount["path"]
        new_paths[path] = ctx
        new_contexts.add(ctx)
    for obj, mountitem in items:        
        assert not is_dummy_mount(obj._mount), obj
        path = obj._mount["path"]
        new_paths[path] = obj
        new_mounts[obj] = mountitem

    old_mountitems = {}
    for old_cell, old_mountitem in list(old_mounts.items()):
        path = old_cell._mount["path"]
        if path in new_paths:
            if isinstance(old_mountitem, MountItem):
                old_mountitem._destroyed = True
            old_mountitems[path] = old_mountitem

    for new_ctx in sorted(new_contexts, key=lambda l: len(l.path)):        
        path = new_ctx._mount["path"]
        if path not in old_paths:
            mountmanager._check_context(new_ctx, False)
    
    for path in sorted(new_paths.keys(), key=lambda p:len(p)):
        cell = new_paths[path]
        if isinstance(cell, Context):
            continue
        obj = new_mounts[cell]        
        if isinstance(obj, MountItem):
            new_mountitem = obj
            if path in old_paths:
                old_mountitem = old_mountitems[path]
                rewrite = False
                cell = new_mountitem.cell()
                buffer, checksum = cell.buffer_and_checksum
                if checksum is not None:
                    if "w" in old_mountitem.mode:
                        if type(old_mountitem.cell()) != type(cell):
                            rewrite = True
                        else:
                            if checksum != old_mountitem.last_checksum:
                                rewrite = True
                if rewrite:
                    with new_mountitem.lock:
                        new_mountitem._write(buffer)
                        new_mountitem._after_write(checksum)
                else:
                    new_mountitem.last_mtime = old_mountitem.last_mtime
                    new_mountitem.last_checksum = old_mountitem.last_checksum
            else:
                new_mountitem.init()
        elif isinstance(obj, LinkItem):
            new_linkitem = obj
            identical = False
            if path in old_mountitems:
                old_linkitem = old_mountitems[path]
                linked = new_linkitem.get_linked()
                if linked._mount["path"] == old_linkitem.linked_path:
                    old = old_linkitem.get_linked()
                    if isinstance(old, Context) and isinstance(linked, Context):
                        identical = True
                    elif isinstance(old, Cell) and isinstance(linked, Cell):
                        identical = True
                if identical:
                    old_linkitem._destroyed = True
                else:
                    old_linkitem.destroy()
            if not identical:
                new_linkitem.init()

class MountManager:
    _running = False
    _last_run = None
    _stop = False
    _mounting = False
    thread = None
    def __init__(self, latency):
        self.latency = latency
        self.mounts = WeakKeyDictionary()
        self.contexts = WeakSet()
        self.lock = RLock()
        self.cell_updates = deque()
        self._tick = Event()
        self.paths = WeakKeyDictionary()

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
    def add_link(self, link, path, persistent):
        paths = self.paths[link._root()]
        assert path not in paths, path
        #print("add link", path, link)
        paths.add(path)
        item = LinkItem(link, path, persistent)
        self.mounts[link] = item
        return item

    @lockmethod
    def unmount(self, cell_or_link, from_del=False):
        assert not is_dummy_mount(cell_or_link._mount), cell_or_link
        root = cell_or_link._root()
        if from_del and (cell_or_link not in self.mounts or root not in self.paths):
            return
        mountitem = self.mounts.pop(cell_or_link)
        if not mountitem._destroyed:
            paths = self.paths[root]
            path = cell_or_link._mount["path"]
            paths.discard(path)            
            mountitem.destroy()

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
        if mount["persistent"] == False:
            dirpath = mount["path"].replace("/", os.sep)
            try:
                #print("rmdir", dirpath)
                os.rmdir(dirpath)
            except Exception:
                print("Error: cannot remove directory %s" % dirpath)

    @lockmethod
    def add_context(self, context, path, as_parent):
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
        dirpath = mount["path"].replace("/", os.sep)
        persistent, authority = mount["persistent"], mount["authority"]
        if os.path.exists(dirpath):
            if authority == "cell" and not as_parent:
                print("Warning: Directory path '%s' already exists" % dirpath) #TODO: log warning
        else:
            if authority == "file-strict":
                raise Exception("Directory path '%s' does not exist, but authority is 'file-strict'" % dirpath)
            os.mkdir(dirpath)

    @lockmethod
    def add_cell_update(self, cell, checksum, buffer):
        if self._mounting:
            return
        assert cell in self.mounts, (cell, hex(id(cell)))
        self.cell_updates.append((cell, checksum, buffer))

    def _run(self):
        cell_updates = {cell: (checksum, buffer) \
            for cell, checksum, buffer in self.cell_updates}
        self.cell_updates.clear()
        for cell, mount_item in list(self.mounts.items()):
            if isinstance(cell, Link):
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
                mount_item.conditional_write(checksum, buffer, with_none=True)
            except Exception:
                exc = traceback.format_exc()
                if exc != mount_item.last_exc:
                    print(exc)
                    mount_item.last_exc = exc
        self._tick.set()

    def run(self):
        try:
            self._running = True
            while not self._stop:
                t = time.time()
                try:
                    self._run()
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


    def destroy(self):
        for path in list(self.mounts.keys()):
            self.unmount(path)
        for context in sorted(self.contexts,key=lambda l:-len(l.path)):
            self.unmount_context(context)

@lockfunc
def scan(ctx_or_cell, *, old_context):
    """Scans a cell or a context and its children for _mount attributes, and mounts them
    If an old context (of the same path) is given, it will be simultaneously unmounted
     (reusing all common mounts)
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
    top_paths = mountmanager.paths[root]

    if old_context is not None:
        assert isinstance(ctx_or_cell, Context)
        assert ctx_or_cell.path == old_context.path, (ctx_or_cell.path, old_context.path)
        new_context = ctx_or_cell
        assert not old_context._part_of(new_context)
        assert not new_context._part_of(old_context)
        assert old_context._root() is root        
    else:
        new_context = None
    old = build_paths(old_context, top_paths, remove=True)

    try:
        ok = False
        mountitems = []
        contexts = set()
        cells = set()
        links = set()
        mounts = mountmanager.mounts.copy()
        if sys.exc_info()[0] is not None:
            return #No mounting if there is an exception
        def find_mount(c, as_parent=False, child=None):
            if as_parent:
                assert child is not None
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
                if isinstance(c, Link):
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
                if isinstance(child, Link):
                    child = child.get_linked()
                if isinstance(child, Cell) and child._mount is None:
                    if child._monitor:
                        raise NotImplementedError # livegraph branch
                    else:
                        livegraph = child._get_manager().livegraph
                        if livegraph.will_lose_authority(child):
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
                    contexts_to_mount[context][1] = False
                return
            parent = context._context
            if parent is not None:
                parent = parent()
                mount_context_delayed(parent, as_parent=True)
            object.__setattr__(context, "_mount", mounts[context]) #not in macro mode
            contexts_to_mount[context] = [mounts[context]["path"], as_parent]
            done_contexts.add(context)

        for context in contexts:
            mount_context_delayed(context)

        def propagate_persistency(c, persistent=False):
            m = c._mount
            if is_dummy_mount(m):
                return
            if persistent:
                m["persistent"] = True
            elif m["persistent"] == True and m["autopath"]:
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
        for link in links:
            if link in mounts and not is_dummy_mount(mounts[link]):
                mount = mounts[link]
                path = mount["path"]
                object.__setattr__(link, "_mount", mount) #not in macro mode
                mount_links.append(link)

        for ctx, args in contexts_to_mount.items():
            mountmanager.add_context(ctx, args[0], args[1])

        for cell in mount_cells:
            mountitem = mountmanager.add_mount(cell, **cell._mount)
            mountitems.append((cell, mountitem))
        for link in mount_links:
            mount = link._mount
            mountitem = mountmanager.add_link(link, mount["path"], mount["persistent"])
            mountitems.append((link, mountitem))
        ok = True
    finally:
        if not ok and old_context is not None:
            _, old_contexts, old_paths = old
            for ctx in old_contexts:
                mountmanager.contexts.add(ctx)
            for path in old_paths:
                cell_or_context = old_paths[path]
                top_paths.add(path)
                if isinstance(cell_or_context, Context):
                    continue
                cell = cell_or_context
                for mcell, mountitem in list(mountmanager.mounts.items()):
                    if mountitem.path == path and mcell is not cell:
                        try:
                            mountitem.destroy()
                        except Exception:
                            pass

    new = build_paths(new_context, top_paths, remove=False)
    try:
        mountmanager._mounting = True
        join(mountitems, contexts_to_mount, new, old)
    finally:
        mountmanager._mounting = False

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

from .link import Link
from .protocol.cson import cson2json
from .protocol.calculate_checksum import calculate_checksum_sync as calculate_checksum