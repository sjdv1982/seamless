from numpy import isin
from .Base import Base

def get_new_module(path):
    return {
        "path": path,
        "type": "module",
        "module_type": "interpreted",
        "language": "python",
        "dependencies": [], 
        "UNTRANSLATED": True,
    }

class Module(Base):
    _virtual_path = None
    _node = None
    _subpath = ()

    def __init__(self, *, parent=None, path=None, language=None):
        assert (parent is None) == (path is None)
        if parent is not None:
            self._init(parent, path)
        if language is not None:
            self.language = language

    def _init(self, parent, path):
        super().__init__(parent=parent, path=path)
        parent._children[path] = self

    def _get_ctx_subpath(self, cell, subpath):
        p = cell
        for path in subpath:
            p2 = getattr(p, path)
            if isinstance(p2, SynthContext) and p2._context is not None:
                p2 = p2._context()
            p = p2
        return p

    def _get_ctx(self):
        parent = self._parent()
        p = parent._gen_context
        if p is None:
            raise ValueError
        if len(self._path):
            pp = self._path[0]
            p2 = getattr(p, pp)
            if isinstance(p2, SynthContext) and p2._context is not None:
                p2 = p2._context()
            p = p2
        return self._get_ctx_subpath(p, self._path[1:])

    def _get_codecell(self):
        return self._get_ctx().code

    def _get_hnode(self):
        parent = self._parent()
        return parent._get_node(self._path)

    def _get_hnode2(self):
        try:
            return self._get_hnode()
        except AttributeError:
            pass
        if self._node is None:
            self._node = get_new_module(None)
        return self._node

    def _observe_codecell(self, checksum):
        if self._parent() is None:
            return
        if self._parent()._translating:
            return
        try:
            hnode = self._get_hnode()
        except Exception:
            return
        if checksum is None:
            hnode.pop("checksum", None)
        else:
            hnode["checksum"] = checksum

    def mount(
        self, path, mode="rw", authority="file", *,
        persistent=True
    ):
        """Mounts the module's code cell to the file system.

        To delete an existing mount, do `del module.mount`

        Arguments
        =========
        - path
          The file path on disk
        - mode
          "r" (read), "w" (write) or "rw".
          If the mode contains "r", the code cell is updated when the file changes on disk.
          If the mode contains "w", the file is updated when the code cell value changes.
          The mode can only contain "r" if the code cell is independent.
          Default: "rw"
        - authority
          In case of conflict between code cell and file, which takes precedence.
          Default: "file".
        - persistent
          If False, the file is deleted from disk when the code cell is destroyed
          Default: True.
        """
        # TODO: check for independence (has_authority)
        # TODO, upon translation: check that there are no duplicate paths.
        hnode = self._get_hnode2()
        mount = {
            "path": path,
            "mode": mode,
            "authority": authority,
            "persistent": persistent
        }
        hnode["mount"] = mount
        if self._parent() is not None:
            self._parent()._translate()
        return self

    def __setattr__(self, attr, value):
        if attr == "code":
            from .assign import assign
            parent = self._parent()
            return assign(parent, self._path, value)
        return object.__setattr__(self, attr, value)

    @property
    def code(self):
        """Returns the code of the module, if translated

        If the module code is not authoritative,
         the value is None if an upstream dependency
         is undefined or has an error.
        """
        parent = self._parent()
        hnode = self._get_hnode()
        if hnode.get("UNTRANSLATED"):
            return None
        try:
            codecell = self._get_codecell()
        except Exception:
            import traceback; traceback.print_exc()
            raise
        if codecell is None:
            raise ValueError
        value = codecell.value
        return value

    @property
    def dependencies(self):
        """Returns the dependencies of the module"""
        hnode = self._get_hnode2()
        return tuple(hnode.get("dependencies", []))

    @dependencies.setter
    def dependencies(self, value):
        deps = []
        for dep in value:
            if not isinstance(dep, str):
                raise TypeError(dep)
            deps.append(dep)
        hnode = self._get_hnode2()
        hnode["dependencies"] = deps
        if self._parent() is not None:
            self._parent()._translate()
        
    async def fingertip(self):
        """Puts the buffer of the code cell's checksum 'at your fingertips':

        - Verify that the buffer is locally or remotely available;
          if remotely, download it.
        - If not available, try to re-compute it using its provenance,
          i.e. re-evaluating any transformation or expression that produced it
        - Such recomputation is done in "fingertip" mode, i.e. disallowing
          use of expression-to-checksum or transformation-to-checksum caches
        """
        parent = self._parent()
        manager = parent._manager
        cachemanager = manager.cachemanager
        checksum = self.checksum
        await cachemanager.fingertip(checksum)

    @property
    def fingertip_no_remote(self):
        """TODO: document"""
        hnode = self._get_hnode2()
        return hnode.get("fingertip_no_remote", False)

    @fingertip_no_remote.setter
    def fingertip_no_remote(self, value):
        if value not in (True, False):
            raise TypeError(value)
        hnode = self._get_hnode2()
        if value == True:
            hnode["fingertip_no_remote"] = True
        else:
            hnode.pop("fingertip_no_remote", None)

    @property
    def fingertip_no_recompute(self):
        """TODO: document"""
        hnode = self._get_hnode2()
        return hnode.get("fingertip_no_recompute", False)

    @fingertip_no_recompute.setter
    def fingertip_no_recompute(self, value):
        if value not in (True, False):
            raise TypeError(value)
        hnode = self._get_hnode2()
        if value == True:
            hnode["fingertip_no_recompute"] = True
        else:
            hnode.pop("fingertip_no_recompute", None)

    @property
    def checksum(self):
        """Contains the checksum of the module code, as SHA3-256 hash.

        The checksum defines the value of the module code.
        If the code cell is defined, the checksum is available, even if
        the value may not be.
        """
        parent = self._parent()
        hnode = self._get_hnode2()
        if hnode.get("UNTRANSLATED"):
            if "TEMP" in hnode:
                codecell = self._get_codecell()
                return codecell.checksum
            return hnode.get("checksum")
        else:
            try:
                codecell = self._get_codecell()
            except Exception:
                import traceback; traceback.print_exc()
                raise
            return codecell.checksum

    @checksum.setter
    def checksum(self, checksum):
        """Sets the checksum of the cell, as SHA3-256 hash"""
        hnode = self._get_hnode2()
        if hnode.get("UNTRANSLATED"):
            hnode["checksum"] = checksum
            return
        codecell = self._get_codecell()
        codecell.set_checksum(checksum)

    def set(self, value):
        """Sets the value of the module's code cell"""
        hnode = self._get_hnode2()
        if hnode.get("UNTRANSLATED"):
            hnode["TEMP"] = value
            return
        codecell = self._get_codecell()
        codecell.set(value)

    def set_checksum(self, checksum):
        self.checksum = checksum

    @property
    def status(self):
        """Returns the status of the module's code cell.

        The status may be undefined, error, upstream or OK
        If it is error, Cell.exception will be non-empty.
        """
        if self._get_hnode().get("UNTRANSLATED"):
            return "Status: error (ctx needs translation)"
        codecell = self._get_codecell()
        return codecell.status

    @property
    def status(self):
        """Returns the status of the module's code cell.

        The status may be undefined, error, upstream or OK
        If it is error, Cell.exception will be non-empty.
        """
        if self._get_hnode().get("UNTRANSLATED"):
            return "Status: error (ctx needs translation)"
        codecell = self._get_codecell()
        return codecell.status

    @property
    def exception(self):
        """Returns the exception associated with the module's code cell.

        If not None, this exception was raised during parsing."""
        if self._get_hnode().get("UNTRANSLATED"):
            return "Status: error (ctx needs translation)"
        codecell = self._get_codecell()
        return codecell.exception

    @property
    def type(self):
        """The type of the module, interpreted or compiled"""
        hnode = self._get_hnode2()
        return hnode["module_type"]

    @type.setter
    def type(self, value):
        if value not in ("interpreted", "compiled"):
            raise ValueError
        if value == "compiled":
            raise NotImplementedError
        hnode = self._get_hnode2()
        old_type = hnode.get("module_type")
        hnode["module_type"] = value
        if value != old_type:
            if self._parent() is not None:
                self._parent()._translate()

    @property
    def language(self):
        """The programming language for code cells.

        Default: Python"""
        hnode = self._get_hnode2()
        return hnode.get("language", "python")

    @language.setter
    def language(self, value):
        if value not in ("python", "ipython"):
            raise NotImplementedError
        from ..compiler import find_language
        hnode = self._get_hnode2()
        lang, language, extension = find_language(value)
        hnode["language"] = lang
        if self._parent() is not None:
            self._parent()._translate()

    def _set_observers(self):
        from ..core.cell import Cell as CoreCell
        codecell = self._get_codecell()
        if not isinstance(codecell, CoreCell):
            raise Exception(codecell)
        codecell._set_observer(self._observe_codecell)

    def __delattr__(self, attr):
        if attr == "mount":
            hnode = self._get_hnode2()
            if attr in hnode:
                hnode.pop(attr)
                if self._parent() is not None:
                    self._parent()._translate()
        else:
            raise AttributeError(attr)


    def __str__(self):
        path = ".".join(self._path) if self._path is not None else None
        return "Seamless Module: %s" % path

from .synth_context import SynthContext