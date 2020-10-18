import sys
from types import ModuleType
from contextlib import contextmanager

class Injector:
    def __init__(self, topmodule_name):
        self.topmodule_name = topmodule_name
        self.topmodule = ModuleType(topmodule_name)
        self.topmodule.__package__ = topmodule_name
        self.topmodule.__path__ = []

    @contextmanager
    def active_workspace(self, workspace, namespace):
        sys_modules = sys.modules
        old_modules = {}
        old_packages = {}
        if self.topmodule_name in sys_modules:
            old_modules[self.topmodule_name] = sys_modules[self.topmodule_name]
        for modname, mod in workspace.items():
            assert mod is not None, modname
            mname = self.topmodule_name + "." + modname
            if mname in sys_modules:
                old_modules[mname] = sys_modules[mname]
        try:
            sys_modules[self.topmodule_name] = self.topmodule
            if self.topmodule_name != "macro":
                namespace[self.topmodule_name] = self.topmodule
            for modname, mod in workspace.items():
                mname = self.topmodule_name + "." + modname
                sys_modules[mname] = mod
                namespace[modname] = mod
                old_packages[modname] = mod.__package__
                mod.__package__ = mname
                mod.__path__ = []
            yield
        finally:
            if self.topmodule_name in old_modules:
                sys_modules[self.topmodule_name] = old_modules[self.topmodule_name]
            else:
                sys_modules.pop(self.topmodule_name, None)
            for modname, mod in workspace.items():
                mname = self.topmodule_name + "." + modname
                if mname in old_packages:
                    mod = sys_modules[mname]
                    mod.__package__ = old_packages[mname]
                if mname in old_modules:
                    sys_modules[mname] = old_modules[mname]
                else:
                    sys_modules.pop(mname, None)


macro_injector = Injector("macro")
transformer_injector = Injector("transformer")
reactor_injector = Injector("reactor")
