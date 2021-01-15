import weakref

from .injector import reactor_injector as injector
from .build_module import build_module

class ReactorInput:
    def __init__(self, value):
        self._value = value
        self.updated = (value is not None)
        self.defined = (value is not None)
    def get(self):
        return self._value
    @property
    def value(self):
        return self.get()

class ReactorOutput:
    def __init__(self, parent, name):
        self._parent = weakref.ref(parent)
        self._name = name
    def _set(self, value, preliminary):
        p = self._parent()
        if p is None:
            return
        p.set_pin(self._name, value, preliminary)
    def set(self, value):
        return self._set(value, False)
    def set_preliminary(self, value):
        return self._set(value, True)

class ReactorEdit:
    _store = None
    def __init__(self, parent, name, value):
        self._parent = weakref.ref(parent)
        self._name = name
        self._value = value
        self.updated = (value is not None)
        self.defined = (value is not None)
    def get(self):
        return self._value
    @property
    def value(self):
        return self.get()
    def _set(self, value, preliminary):
        self._value = value
        self.defined = True
        p = self._parent()
        if p is None:
            return
        p.set_pin(self._name, value, False)
    def set(self, value):
        return self._set(value, False)

class PINS:
    def __getitem__(self, attr):
        return getattr(self, attr)
    def __setitem__(self, attr, value):
        return setattr(self, attr, value)

class RuntimeReactor:
    def __init__(self,
        manager, reactor, inputpins, outputpins, editpins
    ):
        self.manager = weakref.ref(manager)
        self.reactor = weakref.ref(reactor)
        self.inputpins = inputpins
        self.outputpins = outputpins
        self.editpins = editpins
        self.updated = set()
        self.live = False
        self.namespace = {}
        self.module_workspace = {}
        self.values = {}
        self.PINS = PINS()
        self.executing = False

    def prepare_namespace(self, updated):
        manager = self.manager()
        if updated is None:
            self.clear()
        self.namespace["__name__"] = "reactor"
        for pinname in self.inputpins:
            if updated is not None and pinname not in updated:
                if pinname not in ("code_start", "code_update", "code_stop"):
                    self.PINS[pinname].updated = False
                continue
            if pinname in self.module_workspace:
                continue
            value = self.values[pinname]
            if pinname in ("code_start", "code_update", "code_stop"):
                assert value is not None, pinname
                continue
            if not self.live:
                pin = ReactorInput(value)
                self.PINS[pinname] = pin
            else:
                self.PINS[pinname]._value = value
                self.PINS[pinname].updated = True
        for pinname in self.editpins:
            if updated is not None and pinname not in updated:
                self.PINS[pinname].updated = False
                continue
            value = self.values.get(pinname)
            if not self.live:
                pin = ReactorEdit(self, pinname, value)
                self.PINS[pinname] = pin
            else:
                if value == self.PINS[pinname]._value:
                    self.PINS[pinname].updated = False
                else:
                    self.PINS[pinname]._value = value
                    self.PINS[pinname].updated = True
        for pinname in self.outputpins:
            if not self.live:
                pin = ReactorOutput(self, pinname)
                self.PINS[pinname] = pin
        for pinname in self.module_workspace:
            value = self.module_workspace[pinname]
            if not self.live:
                self.PINS[pinname] = ReactorInput(value)
                self.PINS[pinname] = pin
            else:
                self.PINS[pinname]._value = value
            if updated is not None and pinname not in updated:
                self.PINS[pinname].updated = False
            else:
                self.PINS[pinname].updated = True

    def run_code(self, codename):
        assert codename in ("code_start", "code_stop", "code_update")
        code_object = self.values[codename]
        self.namespace["PINS"] = self.PINS
        try:
            if len(self.module_workspace):
                with injector.active_workspace(self.module_workspace, self.namespace):
                    exec(code_object, self.namespace)
            else:
                exec(code_object, self.namespace)
        except Exception as exception:
            self.clear()
            self.manager()._set_reactor_exception(self.reactor(), codename, exception)

    def execute(self):
        assert not self.executing
        self.manager()._set_reactor_exception(self.reactor(), None, None)
        codes = ("code_start", "code_update", "code_stop")
        try:
            self.executing = True
            if self.live and any([c in self.updated for c in codes]):
                self.run_code("code_stop")
                self.clear()
            if not self.live:
                self.prepare_namespace(None)
                self.live = True
                self.run_code("code_start")
            else:
                self.prepare_namespace(self.updated)
            self.run_code("code_update")
        finally:
            self.executing = False
        self.updated.clear()

    def set_pin(self, pinname, value, preliminary):
        from .worker import OutputPin, EditPin
        reactor = self.reactor()
        manager = self.manager()
        livegraph = manager.livegraph
        pin = reactor._pins[pinname]
        assert isinstance(pin, (OutputPin, EditPin))

        if isinstance(pin, EditPin):
            assert not preliminary
            cell = livegraph.editpin_to_cell[reactor][pinname]
            if cell is None:
                return
            manager.set_cell(cell, value)
        else:
            if preliminary:
                raise NotImplementedError
            if not self.executing:
                msg = "%s can set outputpin '%s' only while executing"
                raise Exception(msg % (self.reactor(), pinname))

            downstream = livegraph.reactor_to_downstream[reactor][pinname]
            if not len(downstream):
                celltype, subcelltype = reactor.outputs[pinname]
                if celltype is None:
                    celltype = "plain"
            else:
                wa = downstream[0].write_accessor
                celltype = wa.celltype
                subcelltype = wa.subcelltype
            ReactorResultTask(
                manager, reactor,
                pinname, value,
                celltype, subcelltype
            ).launch()

    def clear(self):
        #print("CLEAR")
        self.namespace.clear()
        self.PINS = PINS()
        self.live = False

    def stop(self):
        if not self.live:
            return
        self.run_code("code_stop")
        self.clear()

from .manager.tasks.reactor_update import ReactorResultTask