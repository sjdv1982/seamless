import sys
from types import ModuleType
from weakref import WeakKeyDictionary
from contextlib import contextmanager
import hashlib
from ..ipython import execute as ipython_execute

class Injector:
    def __init__(self, topmodule_name):
        self.topmodule_name = topmodule_name
        self.workspaces = WeakKeyDictionary()
        self.topmodule = ModuleType(topmodule_name)

    def define_workspace(self, workspace_key, workspace_modules):
        assert workspace_key not in self.workspaces, workspace_key
        ws = {k: None for k in workspace_modules}
        self.workspaces[workspace_key] = ws

    def define_module(self, workspace_key, module_name, language, code):
        assert language in ("python", "ipython", "binary"), language
        ws = self.workspaces[workspace_key]
        mname = self.topmodule_name + "." + module_name
        if language == "binary":
            mod = code
            m = {"module":mod, "name": mname, "checksum": None}
            ws[module_name] = m
            return mod
        if code is None:
            ws[module_name] = None
            return
        else:
            assert isinstance(code, str), type(code)
        m = ws.get(module_name)
        checksum = hashlib.md5(code.encode("utf-8")).hexdigest()
        if m is not None and m["checksum"] == checksum:
            return
        m = {}
        m["name"] = mname
        mod = ModuleType(mname)
        namespace = mod.__dict__
        if language == "ipython":
            ipython_execute(code, namespace)
        else:
            exec(code, namespace)
        m["module"] = mod
        m["checksum"] = checksum
        ws[module_name] = m
        return mod

    @contextmanager
    def active_workspace(self, workspace_key):
        if workspace_key is None:
            yield
            return
        sys_modules = sys.modules
        ws = self.workspaces[workspace_key]
        old_modules = {}
        if self.topmodule_name in sys_modules:
            old_modules[self.topmodule_name] = sys_modules[self.topmodule_name]
        for modname, mod in ws.items():
            assert mod is not None, modname
            mname = mod["name"]
            if mname in sys_modules:
                old_modules[mname] = sys_modules[mname]
        try:
            sys_modules[self.topmodule_name] = self.topmodule
            for modname, mod in ws.items():
                mname = mod["name"]
                sys_modules[mname] = mod["module"]
            yield
        finally:
            if self.topmodule_name in old_modules:
                sys_modules[self.topmodule_name] = old_modules[self.topmodule_name]
            else:
                sys_modules.pop(self.topmodule_name)
            for modname, mod in ws.items():
                mname = mod["name"]
                if mname in old_modules:
                    sys_modules[mname] = old_modules[mname]
                else:
                    sys_modules.pop(mname)

    def clone(self):
        """Returns a cloned injector for pickling"""
        return ClonedInjector(self)

class ClonedInjector(Injector):
    def __init__(self, injector):
        assert isinstance(injector, Injector)
        self.topmodule_name = injector.topmodule_name
        self.workspaces = dict(injector.workspaces)
        self.topmodule_dict = injector.topmodule.__dict__
    def restore(self):
        self.topmodule = ModuleType(self.topmodule_name)
        self.topmodule.__dict__.update(self.topmodule_dict)

macro_injector = Injector("macro")
transformer_injector = Injector("transformer")
reactor_injector = Injector("reactor")
