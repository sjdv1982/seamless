import os
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

    def _check_mount_multi(self, mount):
        if mount is None:
            return
        path = mount["path"]
        last = os.path.split(path)[1]
        if "." in last:
            msg = "Multi-module cannot have a mount path where the last part contains . : {}"
            raise ValueError(msg.format(path))

    def mount(
        self, path, mode="rw", authority="file", *,
        persistent=True
    ):
        """Mounts the module's code to the file system.

        To delete an existing mount, do `del module.mount`

        Arguments
        =========
        - path
          The file path on disk. For a multi-module, this is a directory instead.
        - mode
          "r" (read), "w" (write) or "rw".
          If the mode contains "r", the code is updated when the file changes on disk.
          If the mode contains "w", the file is updated when the module code value changes.
          The mode can only contain "r" if the module code is independent.
          Default: "rw"
        - authority
          In case of conflict between module code and file, which takes precedence.
          Default: "file".
        - persistent
          If False, the file is deleted from disk when the module is destroyed
          Default: True.
        """
        # TODO: check for independence (has_independence)
        # TODO, upon translation: check that there are no duplicate paths.
        hnode = self._get_hnode2()
        mount = {
            "path": path,
            "mode": mode,
            "authority": authority,
            "persistent": persistent
        }
        if self.multi:
            self._check_mount_multi(mount)
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
        hnode = self._get_hnode()
        if hnode.get("UNTRANSLATED"):
            return hnode.get("TEMP")
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
        """Returns the dependencies of the module

This is a list of module names that must be connected
to any Transformer or Macro together with this module.
"""
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

    @property
    def multi(self):
        """If the module is a multi-module
        
Multi-modules consist of multiple files.
The module code is stored as a dict
where the keys are file names and the values are file contents.

Files in subdirectories have the subdirectory in their file name,
e.g. "subdirectory/code.py".
"""
        hnode = self._get_hnode()
        return hnode.get("multi", False)        

    @multi.setter
    def multi(self, value):
        if not isinstance(value, bool):
            raise TypeError(type(value))
        hnode = self._get_hnode()
        if value:
            mount = hnode.get("mount")
            self._check_mount_multi(mount)
            hnode["multi"] = True
        else:
            hnode.pop("multi", None)
        if self._parent() is not None:
            self._parent()._translate()

    @property
    def internal_package_name(self):
        """For Python packages, the name that is used in internal absolute imports

For example, if a package contains "__init__.py", "spam.py" and "ham.py",
then "foo.py" could import "spam.eggs" with a relative import ("from .spam import eggs").
   
Or, it could use an internal package name like "spamalot" and do
"from spamalot.spam import eggs"
"""
        if not self.multi:
            raise AttributeError("Only multi modules can have an internal package name")
        hnode = self._get_hnode()
        return hnode.get("internal_package_name")

    @internal_package_name.setter
    def internal_package_name(self, value: str):
        if not self.multi:
            raise AttributeError("Only multi modules can have an internal package name")
        if not isinstance(value, str):
            raise TypeError(type(value))
        hnode = self._get_hnode()
        hnode["internal_package_name"] = value
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
        hnode = self._get_hnode2()
        if hnode.get("UNTRANSLATED"):
            if "TEMP" in hnode:
                try:
                    codecell = self._get_codecell()
                    return codecell.checksum
                except Exception:
                    raise AttributeError("TEMP value with unknown checksum")
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
            hnode.pop("TEMP", None)
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
        try:
            codecell = self._get_codecell()
        except Exception:
            import traceback; traceback.print_exc()
            raise
        codecell.set(value)

    def set_checksum(self, checksum):
        self.checksum = checksum

    def __setitem__(self, filename, value):
        if not self.multi:
            raise TypeError("Module object only supports item assignment if multi")
        hnode = self._get_hnode2()
        if hnode.get("UNTRANSLATED"):
            if "TEMP" not in hnode:
                temp = {}
                hnode["TEMP"] = temp
                hnode.pop("checksum", None)
            else:
                temp = hnode["TEMP"]
            temp[filename] = value
            hnode["TEMP"] = temp
            return
        try:
            codecell = self._get_codecell()
        except Exception:
            import traceback; traceback.print_exc()
            raise
        code = codecell.value
        if not isinstance(code, dict):
            code = {}
        code[filename] = value
        codecell.set(code)

    def __getitem__(self, filename):
        if not self.multi:
            raise TypeError("Module object is only subscriptable if multi")
        code = self.code
        if code is None:
            return None
        if not isinstance(code, dict):
            raise TypeError("Multi-module code is not a dict")
        return code.get(filename)

    @property
    def status(self):
        """Returns the status of the module's code cell.

        The status may be undefined, error, upstream or OK
        If it is error, Module.exception will be non-empty.
        """
        if self._get_hnode().get("UNTRANSLATED"):
            return "Status: error (ctx needs translation)"
        codecell = self._get_codecell()
        status = codecell.status
        if status == "Status: OK":
            gen_moduledict = self._get_ctx().gen_moduledict  
            status2 = gen_moduledict.status
            if status2 != "Status: OK":
                status = {
                    "gen_moduledict": status2
                }      
        return status


    @property
    def exception(self):
        """Returns the exception associated with the module's code cell.

        If not None, this exception was raised during parsing."""
        if self._get_hnode().get("UNTRANSLATED"):
            return "Status: error (ctx needs translation)"
        codecell = self._get_codecell()
        exception = codecell.exception
        if exception is None and codecell.status == "Status: OK":
            gen_moduledict = self._get_ctx().gen_moduledict  
            exc2 = gen_moduledict.exception
            if exc2 is not None:
                exception = {
                    "gen_moduledict": exc2
                }      
        return exception

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
        parent = self._parent()
        lang, _, _ = parent.environment.find_language(value)
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

    def __repr__(self):
        return str(self)

from .synth_context import SynthContext