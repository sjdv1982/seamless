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

from weakref import WeakValueDictionary, WeakKeyDictionary, ref
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
        print("NEW MOUNT", self.cell())

    def init(self):
        if self._destroyed:
            return
        assert self.parent is not None
        cell = self.cell()
        if cell is None:
            return
        exists = self._exists(on_init=True)
        cell_empty = (cell.status() != "OK")
        if self.authority in ("file", "file-strict"):
            if exists and cell_empty:
                with self.lock:
                    filevalue = self._read(on_init=True)
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
                    checksum = cell.checksum()
                    value = cell.serialize("buffer")
                    with self.lock:
                        self._write(value)
                        self._after_write(checksum)
        else: #self.authority == "cell"
            if not cell_empty:
                checksum = cell.checksum()
                value = cell.serialize("buffer")
                #if "r" in self.mode and self._exists():  #comment out, must read in .storage
                if exists:
                    with self.lock:
                        filevalue = self._read(on_init=True)
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
                        filevalue = self._read(on_init=True)
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

    def _read(self, on_init=False):
        print("read", self.cell())
        if not on_init:
            assert "r" in self.mode
        binary = self.kwargs["binary"]
        encoding = self.kwargs.get("encoding")
        filemode = "rb" if binary else "r"
        with open(self.path.replace("/", os.sep), filemode, encoding=encoding) as f:
            return f.read()

    def _write(self, filevalue):
        print("write", self.cell())
        assert "w" in self.mode
        binary = self.kwargs["binary"]
        encoding = self.kwargs.get("encoding")
        filemode = "wb" if binary else "w"
        with open(self.path.replace("/", os.sep), filemode, encoding=encoding) as f:
            f.write(filevalue)

    def _exists(self, on_init=False):
        if not on_init and not "r" in self.mode:
            return False
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
            value = cell.serialize("buffer")
            assert cell._checksum(value, buffer=True) == checksum, cell.format_path()
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
        if not "r" in self.mode:
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
        cell_checksum = cell.checksum()
        if file_checksum is not None and file_checksum != cell_checksum:
            self.set(filevalue, checksum=file_checksum)

    def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        if self.dummy:
            return
        if self.persistent == False and os.path.exists(self.path):
            print("remove", self.path)
            os.unlink(self.path)

    def __del__(self):
        self.destroy()

class MountManagerStash:
    """Stashes away a part of the mounts that are all under a single context
    They can later be destroyed or restored, depending on what happens to the context
    NOTE: While the stash is active, there are ._mount objects (in cells and contexts)
     and MountItems that point to the same path, but with different cells and contexts
     Therefore, for the duration of the stash, it is imperative that all those are
      kept alive and not garbage-collected, until the stash is undone.
     This means that stashing must be done in a Python context (= with statement)
    """
    def __init__(self, parent):
        self._split = False
        self.mounts = WeakKeyDictionary()
        self.contexts = WeakSet()
        self.parent = parent
        self.context = context
    def activate(self):
        assert not self._split
        self._split = True
        raise NotImplementedError
    def join(self):
        raise NotImplementedError
        """
        for path, v in self.limbo.items():
            cell, mountitem = v
            self._unmount(path, cell)
            object.__setattr__(cell, "_mount", None) #since we are not in macro mode
        dirpaths = sorted(self.limbo_dirpaths.items(),key=lambda l:-len(l[0]))
        for dirpath, context in dirpaths:
            self._unmount_dirpath(dirpath)
            object.__setattr__(context, "_mount", None) #since we are not in macro mode
        """
        """
                if self.from_limbo:
                    last_checksum, last_mtime = self.parent().limbo_stats[self.path]
                    if last_checksum == checksum:
                        do_write = False
                        self.last_mtime = last_mtime
        mountitem.init()
        """
    def undo(self):
        raise NotImplementedError
        """
        print("reorganizing failure", self.limbo_dirpaths)
        # why???
        dirpaths = sorted(self.limbo_dirpaths.items(),key=lambda l:-len(l[0]))
        for dirpath, context in dirpaths:
            mount = context._mount
            self.add_context(self, context, dirpath, mount["persistent"], mount["authority"], True)
            for childname, child in context._children.items():
                if getattr(child, "_mount", None) is not None:
                    self._unmount(child.path, child)
            object.__setattr__(context, "_unmounted" , True) #out of macro mode
        print("reorganizing failure...", list(self.limbo.keys()))
        for path, v in self.limbo.items():
            cell, mountitem = v
            self.path_to_cell[path] = cell
            self.mounts[cell] = mountitem
        print("reorganizing failure")
        """

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

    @contextmanager
    def reorganize(self, context):
        if self.stash is not None:
            assert context._part_of(self.stash.context)
            yield
            return
        self.stash = MountManagerStash(context)
        try:
            self.stash.activate()
            yield
            print("reorganize success")
            self.stash.join()
        except Exception as e:
            print("reorganize failure")
            self.stash.undo()
            raise e
        finally:
            self.stash = None

    def add_mount(self, cell, path, mode, authority, persistent, **kwargs):
        assert path not in self.path_to_cell, path
        self.path_to_cell[path] = cell
        self.mounts[cell] = MountItem(self, cell, path, mode, authority, persistent, **kwargs)
        self.mounts[cell].init()

    def _unmount(self, cell):
        mountitem = self.mounts.pop(cell)
        mountitem.destroy()

    def unmount(self, path, cell, from_del=False):
        if self.reorganizing:
            if path in self.limbo:
                assert self.limbo[path][0].cell() is cell, (path, self.limbo[path][0].cell(), cell)
                return
            if path in self.limbo_restored:
                assert self.limbo_restored[path] is cell, (path, self.limbo_restored[path], cell)
                return
        if self.path_to_cell.get(path, None) is not cell:
            if from_del:
                return
            print("Warning: mounted path %s does not point to cell %s" % (path, cell))
            return
        if self.reorganizing:
            print("reorganizing unmount", cell)
            self.path_to_cell.pop(path)
            mountitem = self.mounts[cell]
            self.limbo[path] = cell, mountitem
            self.limbo_stats[path] = mountitem.last_checksum, mountitem.last_mtime
        else:
            self._unmount(path, cell)

    def unmount_context(self, context):
        self.contexts.discard(context) # may or may not exist, especially at __del__ time
        if context._mount is None:
            """THIS is the authoritative one.
            If context is destroyed while an unmount is undesired,
              (because of stash replacement)
            context._mount MUST have been set to None!
            """
            mount = context._mount
            if not mount["persistent"]:
                dirpath = mount["path"]
                try:
                    print("rmdir", dirpath)
                    os.rmdir(dirpath)
                except:
                    print("Error: cannot remove directory %s" % dirpath)


    def add_context(self, context):
        mount = context._mount
        self.con
        dirpath = mount["path"].replace("/", os.sep)
        print("add_context", dirpath)
        persistent, authority = mount["persistent"], mount["authority"]
        """
        in_limbo = False
        if self.reorganizing:
            print("reorganizing add_context", dirpath)
            in_limbo = (dirpath in self.limbo_dirpaths)
            print("IN LIMBO", in_limbo)
            if in_limbo:
                self.limbo_dirpaths.pop(dirpath)
        self.contextpath_to_dirpath[context.path] = dirpath
        if persistent == False:
            self.nonpersistent_dirpaths.add(dirpath)
        """
        if self.stash is None:
            self._check_context(context)

    def _check_context(self, context):
        if os.path.exists(dirpath):
            if authority == "cell" and not in_limbo and not as_parent:
                print("Warning: Directory path '%s' already exists" % dirpath) #TODO: log warning
        else:
            if authority == "file-strict":
                raise Exception("Directory path '%s' does not exist, but authority is 'file-strict'" % dirpath)
            os.mkdir(dirpath)

    def add_cell_update(self, cell):
        assert cell in self.mounts
        self.cell_updates.append(cell)

    def _run(self):
        for cell, mount_item in list(self.mounts.items()):
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
            self._unmount(path)
        dirpaths = self.nonpersistent_dirpaths | set(self.limbo_dirpaths.keys())
        dirpaths = sorted(dirpaths,key=lambda l:-len(l))
        for dirpath in dirpaths:
            self._unmount_dirpath(dirpath)

    def __del__(self):
        self.destroy()

def resolve_register(reg):
    from .context import Context
    from .cell import Cell
    from .structured_cell import Inchannel, Outchannel
    contexts = set([r for r in reg if isinstance(r, Context)])
    cells = set([r for r in reg if isinstance(r, Cell)])
    mounts = mountmanager.mounts.copy()
    print("REG?")
    if sys.exc_info()[0] is not None:
        return #No mounting if there is an exception
    print("REG", list(reg))
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
            result = find_mount(parent, as_parent=True,child=c)
        mounts[c] = result
        if as_parent and result is not None:
            result = copy.deepcopy(result)
            if result["persistent"] is None:
                result["persistent"] = False
            result["path"] += "/" + child.name
            result["path"] += get_extension(child)
        return result
    for r in reg:
        find_mount(r)

    done_contexts = set()
    mount_contexts = set()
    def create_dir(context, as_parent=False):
        if not context in mounts or mounts[context] is None:
            return
        if context in done_contexts:
            return
        parent = context._context
        if parent is not None:
            parent = parent()
            create_dir(parent, as_parent=True)
        mount = mounts[context]


        mount_contexts[context] = path,  mount["persistent"], mount["authority"], as_parent
        done_contexts.add(context)

    for context in contexts:
        create_dir(context)

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
            if mount["persistent"]:
                p = cell._context
                while p is not None:
                    p = p()
                    if p not in contexts:
                        break
                    v = mount_contexts[p]
                    mount_contexts[p] = v[0], True  #make persistent
                    p = p._context
            print("SET _MOUNT", cell, mount)
            cell._mount = mount
            mount_cells.append((cell, mount))
    for context in mount_contexts.items():
        mountmanager.add_context(context)
    for cell, mount in mount_cells:
        mountmanager.add_mount(cell, **mount)

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
TODO: remount option (different [but same-value] cell, same path, for caching); must be in reorganize mode
*****
"""
