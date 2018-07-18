"""
For now, there is a single _read() and a single _write() method, tied to the
 file system. In the future, these will be code cells in a context, and it
 will be possible to register custom _read() and _write() cells, e.g. for
 storage in a database.
Same for _exists.

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
from threading import Thread, RLock, Event
from collections import deque, OrderedDict
import sys, os
import time
import traceback
import copy
from contextlib import contextmanager

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
        assert mode in ("r", "w", "rw"), mode #read from file, write to file, or both
        self.mode = mode
        assert persistent in (True, False, None)
        assert authority in ("cell", "file", "file-strict"), authority
        if authority == "file-strict":
            assert persistent
        if authority == "cell":
            assert "w" in self.mode, (authority, mode)
        elif authority in ("file", "file-strict"):
            assert "r" in self.mode, (authority, mode)
        self.authority = authority
        self.kwargs = kwargs
        self.last_checksum = None
        self.last_time = None
        self.last_mtime = None
        self.persistent = persistent
        self.dummy = dummy

    def init(self):
        if self._destroyed:
            return
        assert self.parent is not None
        cell = self.cell()
        if cell is None:
            return
        exists = self._exists()
        cell_empty = (cell.status() != "OK")
        if self.authority in ("file", "file-strict"):
            if exists and cell_empty:
                with self.lock:
                    filevalue = self._read()
                    update_file = True
                    if not cell_empty:
                        file_checksum = cell._checksum(filevalue, buffer=True)
                        if file_checksum == cell.checksum():
                            update_file = False
                        else:
                            print("Warning: File path '%s' has a different value, overwriting cell" % self.path) #TODO: log warning
                    self._after_read(file_checksum)
                if update_file:
                    self.set(filevalue, checksum=file_checksum)
            elif self.authority == "file-strict":
                raise Exception("File path '%s' does not exist, but authority is 'file-strict'" % self.path)
            else:
                if "w" in self.mode and not cell_empty:
                    value, checksum = cell.serialize("buffer")
                    with self.lock:
                        self._write(value)
                        self._after_write(checksum)
        else: #self.authority == "cell"
            if not cell_empty:
                value, checksum = cell.serialize("buffer")
                #if "r" in self.mode and self._exists():  #comment out, must read in .storage
                if exists:
                    with self.lock:
                        filevalue = self._read()
                        file_checksum = cell._checksum(filevalue, buffer=True)
                        if file_checksum != checksum:
                            print("Warning: File path '%s' has a different value, overwriting file" % self.path) #TODO: log warning
                        self._after_read(file_checksum)
                with self.lock:
                    self._write(value)
                    self._after_write(checksum)
            else:
                #if "r" in self.mode and self._exists(): #comment out, must read in .storage
                if exists:
                    with self.lock:
                        filevalue = self._read()
                        file_checksum = cell._checksum(filevalue, buffer=True)
                        self.set(filevalue, checksum=file_checksum)
                        self._after_read(file_checksum)

    def set(self, filevalue, checksum):
        if self._destroyed:
            return
        cell = self.cell()
        if cell is None:
            return
        if cell._mount_setter is not None:
            cell._mount_setter(filevalue, checksum)
        else:
            cell.set_from_buffer(filevalue, checksum=checksum)

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
            return f.read()

    def _write(self, filevalue):
        #print("write", self.cell())
        assert "w" in self.mode
        binary = self.kwargs["binary"]
        encoding = self.kwargs.get("encoding")
        filemode = "wb" if binary else "w"
        filepath = self.path.replace("/", os.sep)
        if os.path.exists(filepath):
            os.unlink(filepath)
        with open(filepath, filemode, encoding=encoding) as f:
            f.write(filevalue)

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

    def conditional_write(self):
        if self._destroyed:
            return
        if not "w" in self.mode:
            return
        cell = self.cell()
        if cell is None:
            return
        if cell.status() != "OK":
            return
        checksum = cell.checksum()
        if self.last_checksum != checksum:
            value, _ = cell.serialize("buffer")
            assert cell._checksum(value, buffer=True) == checksum, cell._format_path()
            with self.lock:
                self._write(value)
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
            stat = os.stat(self.path)
            mtime = stat.st_mtime
            file_checksum = None
            if self.last_mtime is None or mtime > self.last_mtime:
                filevalue = self._read()
                file_checksum = cell._checksum(filevalue, buffer=True)
                self._after_read(file_checksum, mtime=mtime)
        cell_checksum = None
        if cell.value is not None:
            cell_checksum = cell.checksum()
        if file_checksum is not None and file_checksum != cell_checksum:
            if "r" in self.mode:
                self.set(filevalue, checksum=file_checksum)
            else:
                print("Warning: write-only file %s (%s) has changed on disk, overruling" % (self.path, self.cell()))
                value, _ = cell.serialize("buffer")
                assert cell._checksum(value, buffer=True) == cell_checksum, cell._format_path()
                with self.lock:
                    self._write(value)
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
        if linked._mount is None:
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


class MountManagerStash:
    """Stashes away a part of the mounts that are all under a single context
    They can later be destroyed or restored, depending on what happens to the context
    NOTE: While the stash is active, there are ._mount objects (in cells and contexts)
     and MountItems that point to the same path, but with different cells and contexts
     Therefore, for the duration of the stash, it is imperative that all those are
      kept alive and not garbage-collected, until the stash is undone.
     This means that stashing must be done in a Python context (= with statement)
    """
    def __init__(self, parent, context):
        self._active = False
        self.parent = parent
        self.context = context
        self.mounts = WeakKeyDictionary()
        self.contexts = WeakSet()
        self.context_as_parent = WeakKeyDictionary()
        self.paths = set()

    def activate(self):
        assert not self._active
        self._active = True
        parent, context = self.parent, self.context
        for ctx in list(parent.contexts):
            assert ctx._mount is not None, ctx
            if ctx._part_of2(context):
                self.contexts.add(ctx)
                parent.contexts.remove(ctx)
                path = ctx._mount["path"]
                parent.paths.remove(path)
                self.paths.add(path)
        for cell, mountitem in list(parent.mounts.items()):
            assert cell._mount is not None, cell
            ctx = cell._context()
            assert ctx is not None, cell
            if ctx._part_of2(context):
                self.mounts[cell] = mountitem
                parent.mounts.pop(cell)
                path = cell._mount["path"]
                parent.paths.remove(path)
                self.paths.add(path)

    def _build_new_paths(self):
        """paths added by the parent since stash activation"""
        new_paths = {}

        parent, context = self.parent, self.context
        for ctx in list(parent.contexts):
            path = ctx._mount["path"]
            if ctx._part_of2(context):
                new_paths[path] = ctx
        for cell, mountitem in list(parent.mounts.items()):
            assert cell._mount is not None, cell
            ctx = cell._context()
            if ctx._part_of2(context):
                path = cell._mount["path"]
                new_paths[path] = mountitem
        return new_paths

    def undo(self):
        from .context import Context
        assert self._active
        new_paths = self._build_new_paths()
        parent, context = self.parent, self.context
        for ctx in sorted(self.contexts, key=lambda l: -len(l.path)):
            assert ctx._mount is not None, ctx
            path = ctx._mount["path"]
            if path in new_paths:
                new_context = new_paths[path]
                object.__setattr__(new_context, "_mount", None) #since we are not in macro mode
                new_paths.pop(path)
            parent.contexts.add(ctx)
            parent.paths.add(path)
        for cell, mountitem in self.mounts.items():
            assert cell._mount is not None, cell
            path = cell._mount["path"]
            if path in new_paths:
                new_mountitem = new_paths[path]
                new_mountitem._destroyed = True
                if isinstance(mountitem, LinkItem):
                    new_link = new_mountitem.link()
                    object.__setattr__(new_link, "_mount", None) #since we are not in macro mode
                else:
                    new_cell = new_mountitem.cell()
                    object.__setattr__(new_cell, "_mount", None) #since we are not in macro mode
                new_paths.pop(path)
            parent.mounts[cell] = mountitem
            parent.paths.add(path)

        context_to_unmount = []
        for path, obj in new_paths.items():
            if isinstance(obj, Context):
                context_to_unmount.append(obj)
            elif isinstance(obj, LinkItem):
                parent.unmount(obj.link())
            else:
                parent.unmount(obj.cell())

        for context in sorted(context_to_unmount, key=lambda l: -len(l.path)):
            parent.unmount_context(context)

    def join(self):
        from .context import Context
        from .cell import Cell
        assert self._active
        new_paths = self._build_new_paths()
        parent, context = self.parent, self.context

        old_mountitems = {}
        for old_cell, old_mountitem in list(self.mounts.items()):
            assert old_cell._mount is not None, cell
            path = old_cell._mount["path"]
            object.__setattr__(old_cell, "_mount", None) #since we are not in macro mode
            if path in new_paths:
                if isinstance(old_mountitem, MountItem):
                    old_mountitem._destroyed = True
                old_mountitems[path] = old_mountitem
            else:
                old_mountitem.destroy()

        old_paths = set()
        for old_ctx in sorted(self.contexts, key=lambda l: -len(l.path)):
            assert old_ctx._mount is not None, old_ctx
            path = old_ctx._mount["path"]
            if path in new_paths:
                old_paths.add(path)
                new_context = new_paths[path]
                object.__setattr__(old_ctx, "_mount", None) #since we are not in macro mode
        for path in sorted(new_paths.keys(), key=lambda p:len(p)):
            obj = new_paths[path]
            if isinstance(obj, Context):
                new_context = obj
                if path not in old_paths:
                    assert new_context in self.context_as_parent, context
                    parent._check_context(new_context, self.context_as_parent[new_context])
        for path in sorted(new_paths.keys(), key=lambda p:len(p)):
            obj = new_paths[path]
            if isinstance(obj, MountItem):
                new_mountitem = obj
                #print("new_path", obj, hex(id(obj)), path in old_mountitems)
                if path in old_mountitems:
                    old_mountitem = old_mountitems[path]
                    rewrite = False
                    value, checksum = new_mountitem.cell().serialize("buffer")
                    if type(old_mountitem.cell()) != type(new_mountitem.cell()):
                        rewrite = True
                    else:
                        if checksum != old_mountitem.last_checksum:
                            rewrite = True
                    if rewrite and value is not None:
                        with new_mountitem.lock:
                            new_mountitem._write(value)
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
    def __init__(self, latency):
        self.latency = latency
        self.mounts = WeakKeyDictionary()
        self.contexts = WeakSet()
        self.lock = RLock()
        self.cell_updates = deque()
        self._tick = Event()
        self.stash = None
        self.paths = set()

    @property
    def reorganizing(self):
        return self.stash is not None

    @contextmanager
    def reorganize(self, context):
        if context is None:
            yield
            return
        if self.stash is not None:
            assert context._part_of2(self.stash.context)
            yield
            return
        with self.lock:
            self.stash = MountManagerStash(self, context)
            try:
                self.stash.activate()
                yield
                #print("reorganize success")
                self.stash.join()
            except Exception as e:
                #print("reorganize failure")
                self.stash.undo()
                raise e
            finally:
                self.stash = None

    def add_mount(self, cell, path, mode, authority, persistent, **kwargs):
        assert path not in self.paths, path
        #print("add mount", path, cell)
        self.paths.add(path)
        self.mounts[cell] = MountItem(self, cell, path, mode, authority, persistent, **kwargs)
        if self.stash is None:
            self.mounts[cell].init()

    def add_link(self, link, path, persistent):
        assert path not in self.paths, path
        #print("add link", path, link)
        self.paths.add(path)
        self.mounts[link] = LinkItem(link, path, persistent)
        if self.stash is None:
            self.mounts[link].init()

    def unmount(self, cell_or_link, from_del=False):
        #print("unmount", cell_or_link, hex(id(cell_or_link)))
        assert cell_or_link._mount is not None
        if from_del and cell_or_link not in self.mounts:
            return
        path = cell_or_link._mount["path"]
        assert path in self.paths
        self.paths.remove(path)
        assert cell_or_link in self.mounts, (cell_or_link, path)  #... but path is in self.paths
        mountitem = self.mounts.pop(cell_or_link)
        mountitem.destroy()

    def unmount_context(self, context, from_del=False):
        #print("unmount context", context)
        self.contexts.discard(context) # may or may not exist, especially at __del__ time
        mount = context._mount
        """context._mount is authoritative!
        If context is destroyed while an unmount is undesired,
          (because of stash replacement)
        context._mount MUST have been set to None!
        """
        assert mount is not None, context
        self.paths.remove(mount["path"])
        if mount["persistent"] == False:
            dirpath = mount["path"].replace("/", os.sep)
            try:
                #print("rmdir", dirpath)
                os.rmdir(dirpath)
            except:
                print("Error: cannot remove directory %s" % dirpath)


    def add_context(self, context, path, as_parent):
        #print("add context", path, context, as_parent, context._mount["persistent"])
        if not as_parent:
            assert path not in self.paths, path
            self.paths.add(path)
            self.contexts.add(context)
        else:
            if path in self.paths:
                assert context in self.contexts, (path, context)
        if self.stash is None:
            self._check_context(context, as_parent)
        else:
            self.stash.context_as_parent[context] = as_parent

    def _check_context(self, context, as_parent):
        mount = context._mount
        assert mount is not None, context
        dirpath = mount["path"].replace("/", os.sep)
        persistent, authority = mount["persistent"], mount["authority"]
        if os.path.exists(dirpath):
            if authority == "cell" and not as_parent:
                print("Warning: Directory path '%s' already exists" % dirpath) #TODO: log warning
        else:
            if authority == "file-strict":
                raise Exception("Directory path '%s' does not exist, but authority is 'file-strict'" % dirpath)
            os.mkdir(dirpath)

    def add_cell_update(self, cell):
        assert cell in self.mounts, (cell, hex(id(cell)))
        self.cell_updates.append(cell)

    def _run(self):
        from . import Link
        for cell, mount_item in list(self.mounts.items()):
            if isinstance(cell, Link):
                continue
            if cell in self.cell_updates:
                continue
            try:
                mount_item.conditional_read()
            except Exception:
                exc = traceback.format_exc()
                if exc != mount_item.last_exc:
                    print(exc)
                    mount_item.last_exc = exc
        while 1:
            try:
                cell = self.cell_updates.popleft()
            except IndexError:
                break
            mount_item = self.mounts.get(cell)
            if mount_item is None: #cell was deleted
                continue
            try:
                mount_item.conditional_write()
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
                self._run()
                while time.time() - t < self.latency:
                    if not self._tick.is_set():
                        break
                    time.sleep(0.01)
        finally:
            self._running = False

    def start(self):
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
        self._tick.clear()
        self._tick.wait()

    def destroy(self):
        for path in list(self.mounts.keys()):
            self.unmount(path)
        for context in sorted(self.contexts,key=lambda l:-len(l.path)):
            self.unmount_context(context)

def resolve_register(reg):
    from .context import Context
    from .cell import Cell
    from . import Link
    from .structured_cell import Inchannel, Outchannel
    contexts = set([r for r in reg if isinstance(r, Context)])
    cells = set([r for r in reg if isinstance(r, Cell)])
    links = set([r for r in reg if isinstance(r, Link)])
    mounts = mountmanager.mounts.copy()
    if sys.exc_info()[0] is not None:
        return #No mounting if there is an exception
    def find_mount(c, as_parent=False, child=None):
        if as_parent:
            assert child is not None
        if c in mounts:
            result = mounts[c]
        elif c._mount is not None:
            result = c._mount.copy()
            if result["path"] is None:
                parent = c._context
                assert parent is not None, c
                parent = parent()
                parent_result = find_mount(parent, as_parent=True,child=c)
                if parent_result is None:
                    raise Exception("No path provided for mount of %s, but no ancestor context is mounted" % c)
                result["path"] = parent_result["path"]
        elif isinstance(c, (Inchannel, Outchannel)):
            result = None
        elif isinstance(c, Context) and c._toplevel:
            result = None
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
        mounts[c] = result
        if as_parent and result is not None:
            result = copy.deepcopy(result)
            if result["persistent"] is None:
                result["persistent"] = False
            result["path"] += "/" + child.name
            if isinstance(child, Link):
                child = child.get_linked()
            result["path"] += get_extension(child)
        return result
    for r in reg:
        find_mount(r)

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
        if persistent:
            m["persistent"] = True
        elif m["persistent"] == True:
            persistent = True
        if isinstance(c, Context):
            if c._toplevel:
                return
        parent = c._context
        assert parent is not None, c
        parent = parent()
        propagate_persistency(parent, persistent)
    for r in reg:
        if r._mount is not None:
            propagate_persistency(r)

    mount_cells = []
    for cell in cells:
        if cell in mounts and mounts[cell] is not None:
            mount = mounts[cell]
            path = mount["path"]
            if cell._mount_kwargs is None:
                print("Warning: Unable to mount file path '%s': cannot mount this type of cell (%s)" % (path, type(cell).__name__))
                continue
            mount.update(cell._mount_kwargs)
            if cell._slave and (cell._mount_setter is None):
                if mount.get("mode") == "r":
                    continue
                else:
                    mount["mode"] = "w"
            object.__setattr__(cell, "_mount", mount) #not in macro mode
            mount_cells.append(cell)

    mount_links = []
    for link in links:
        if link in mounts and mounts[link] is not None:
            mount = mounts[link]
            path = mount["path"]
            object.__setattr__(link, "_mount", mount) #not in macro mode
            mount_links.append(link)

    for context, v in contexts_to_mount.items():
        path, as_parent = v
        mountmanager.add_context(context, path, as_parent=as_parent)
    for cell in mount_cells:
        mountmanager.add_mount(cell, **cell._mount)
    for link in mount_links:
        mount = link._mount
        mountmanager.add_link(link, mount["path"], mount["persistent"])

mountmanager = MountManager(0.2) #TODO: latency in config cell
mountmanager.start()

def get_extension(c):
    from .cell import extensions
    for k,v in extensions.items():
        if isinstance(c, k):
            return v
    return ""

"""
*****
TODO: filehash option (cell stores hash of the file, necessary for slash-0)
*****
"""
