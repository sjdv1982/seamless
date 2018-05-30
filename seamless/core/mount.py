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
"""

from weakref import WeakValueDictionary, WeakKeyDictionary, ref
from threading import Thread, RLock, Event
from collections import deque
import os
import time
import traceback

class MountItem:
    last_exc = None
    parent = None
    def __init__(self, parent, cell, path, mode, authority, **kwargs):
        if parent is not None:
            self.parent = ref(parent)
        self.path = path
        self.cell = ref(cell)
        assert mode in ("r", "w", "rw"), mode #read from file, write to file, or both
        self.mode = mode
        assert authority in ("cell", "file", "file-strict"), authority
        if authority == "cell":
            assert "w" in self.mode, (authority, mode)
        elif authority in ("file", "file-strict"):
            assert "r" in self.mode, (authority, mode)
        self.authority = authority
        self.kwargs = kwargs
        self.last_checksum = None
        self.last_time = None
        self.last_mtime = None

    def init(self):
        assert self.parent is not None
        cell = self.cell()
        if cell is None:
            return
        exists = self._exists()
        cell_empty = (cell.status() != "OK")
        if self.authority in ("file", "file-strict"):
            if exists:
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
                    cell.set_from_buffer(filevalue, checksum=file_checksum)
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
                if "r" in self.mode and self._exists():
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
                if "r" in self.mode and self._exists():
                    with self.lock:
                        filevalue = self._read()
                        file_checksum = cell._checksum(filevalue, buffer=True)
                        cell.set_from_buffer(filevalue, checksum=file_checksum)
                        self._after_read(file_checksum)

    @property
    def lock(self):
        assert self.parent is not None
        return self.parent().lock

    def _read(self):
        assert "r" in self.mode
        binary = self.kwargs["binary"]
        encoding = self.kwargs.get("encoding")
        filemode = "rb" if binary else "r"
        with open(self.path.replace("/", os.sep), filemode, encoding=encoding) as f:
            return f.read()

    def _write(self, filevalue):
        assert "w" in self.mode
        binary = self.kwargs["binary"]
        encoding = self.kwargs.get("encoding")
        filemode = "wb" if binary else "w"
        with open(self.path.replace("/", os.sep), filemode, encoding=encoding) as f:
            f.write(filevalue)

    def _exists(self):
        if not "r" in self.mode:
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

    def conditional_read(self):
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
                file_checksum = cell._checksum(filevalue)
                self._after_read(file_checksum, mtime=mtime)
        cell_checksum = cell.checksum()
        if file_checksum is not None and file_checksum != cell_checksum:
            cell.set_from_buffer(filevalue, checksum=file_checksum)

class MountManager:
    _running = False
    _last_run = None
    _stop = False
    def __init__(self, latency):
        self.latency = latency
        self.path_to_cell = WeakValueDictionary()
        self.mounts = WeakKeyDictionary()
        self.lock = RLock()
        self.cell_updates = deque()
        self._tick = Event()

    def add_mount(self, cell, path, mode, authority, **kwargs):
        assert path not in self.path_to_cell
        self.path_to_cell[path] = cell
        self.mounts[cell] = MountItem(self, cell, path, mode, authority, **kwargs)
        self.mounts[cell].init()

    def add_cell_update(self, cell):
        assert cell in self.mounts
        self.cell_updates.append(cell)

    def _run(self):
        for cell, mount_item in self.mounts.items():
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

def resolve_register(reg):
    from .context import Context
    from .cell import Cell
    from .structured_cell import MixedInchannel, MixedOutchannel
    contexts = set([r for r in reg if isinstance(r, Context)])
    cells = set([r for r in reg if isinstance(r, Cell)])
    mounts = {}
    def find_mount(c):
        if c in mounts:
            return mounts[c]
        if c._mount is not None:
            result = c._mount
        elif isinstance(c, (MixedInchannel, MixedOutchannel)):
            result = None
        elif isinstance(c, Context) and c._toplevel:
            result = None
        else:
            parent = c._context
            assert parent is not None, c
            result = find_mount(parent)
            if result is not None:
                result = result.copy()
                result["path"] += "/" + c.name
        if result is not None:
            mounts[c] = result
        return result
    for r in reg:
        find_mount(r)

    done_contexts = set()
    def create_dir(context):  #TODO: this is currently hard-coded, need to be adapted for databases etc.
        if not context in mounts:
            return
        if context in done_contexts:
            return
        parent = context._context
        if parent is not None:
            create_dir(parent)
        mount = mounts[context]
        path = mount["path"].replace("/", os.sep)
        if os.path.exists(path):
            if mount["authority"] == "cell":
                print("Warning: Directory path '%s' already exists" % path) #TODO: log warning
        elif mount["authority"] == "file-strict":
            raise Exception("Directory path '%s' does not exist, but authority is 'file-strict'" % path)
        else:
            os.mkdir(path)
        done_contexts.add(context)

    all_cells = []
    for context in contexts:
        create_dir(context)
        for child in context._children:
            if isinstance(child, Cell) and cell not in cells:
                all_cells.append(child)
    all_cells += list(cells)

    for cell in cells:
        if cell in mounts:
            mount = mounts[cell]
            path = mount["path"]
            if cell._mount_kwargs is None:
                print("Warning: Unable to mount file path '%s': cannot mount this type of cell" % path)
                continue
            mount.update(cell._mount_kwargs)
            if cell._slave:
                if mount.get("mode") == "r":
                    continue
                else:
                    mount["mode"] = "w"
            cell._mount = mount
            mountmanager.add_mount(cell, **mount)

mountmanager = MountManager(0.2)
mountmanager.start()

"""
*****
TODO: filehash option (cell stores hash of the file, necessary for slash-0)
TODO: remount option (different cell, same path, for caching)
TODO: cleanup option (remove file when mount is destroyed; also for contexts!)
*****
"""
