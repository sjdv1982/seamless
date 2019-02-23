import weakref

from .cached_compile import cached_compile

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
    def __init__(self, manager, reactor):
        self.manager = weakref.ref(manager)
        self.reactor = weakref.ref(reactor)
        self.input_dict = {} #inputpin => accessor
        self.output_dict = {} #outputpin => list-of-(cell, subpath)
        self.edit_dict = {} #editpin => (cell, subpath)
        self.updated = set()
        self.live = None  # None for unconnected; True for live; False for non-live
        self.namespace = {}
        self.PINS = PINS()
        self.code_start = None
        self.code_update = None
        self.code_stop = None
        self.executing = False
    
    def prepare_namespace(self, updated):
        manager = self.manager()
        if updated is None:
            self.clear()
        for pinname, accessor in self.input_dict.items():            
            if updated is not None and pinname not in updated:
                if pinname not in ("code_start", "code_update", "code_stop"):
                    self.PINS[pinname].updated = False
                continue
            expression = manager.build_expression(accessor)
            if expression is None:
                value = None
            else:
                value = manager.get_expression(expression)
            if pinname in ("code_start", "code_update", "code_stop"):
                assert value is not None, pinname
                self.build_code(pinname, value)
                continue
            if expression.access_mode == "mixed":
                if value is not None:
                    value = value[2]
            pin = ReactorInput(value)
            self.PINS[pinname] = pin
        for pinname, cell_tuple in self.edit_dict.items():
            cell, subpath = cell_tuple
            if subpath is not None: raise NotImplementedError ### cache branch
            if updated is not None and pinname not in updated:
                self.PINS[pinname].updated = False
                continue
            value = cell.value
            pin = ReactorEdit(self, pinname, value)
            self.PINS[pinname] = pin
        for pinname, cell in self.output_dict.items():
            pin = ReactorOutput(self, pinname)
            self.PINS[pinname] = pin

    def build_code(self, codename, code):
        assert codename in ("code_start", "code_stop", "code_update")
        identifier = str(self.reactor()) + ":" + codename
        try:
            code_object = cached_compile(code, identifier, "exec")
        except Exception as exception:
            self.manager().set_reactor_exception(self, codename, exception)
        setattr(self, codename, code_object)

    def run_code(self, codename):
        #print("REACTOR RUN CODE", codename, self.updated)
        assert codename in ("code_start", "code_stop", "code_update")
        code_object = getattr(self, codename)        
        self.namespace["PINS"] = self.PINS
        try:
            exec(code_object, self.namespace) 
        except Exception as exception:
            self.manager().set_reactor_exception(self, codename, exception)

    def execute(self):
        assert self.live in (True, False)
        assert len(self.updated)
        assert not self.executing
        codes = ("code_start", "code_update", "code_stop")
        try:
            self.executing = True
            if self.live and any([c in self.updated for c in codes]):
                self.run_code("code_stop")
                self.clear()
                self.live = False
            if not self.live:
                self.prepare_namespace(None)
                self.live = True
                self.run_code("code_start")
            else:
                self.prepare_namespace(self.updated)
            self.run_code("code_update")
            if self.reactor().pure == True:
                self.run_code("code_stop")
                self.clear()
                self.live = False
        finally:
            self.executing = False
        #manager.set_reactor_result
        #manager.set_reactor_exception

    def set_pin(self, pinname, value, preliminary):
        from .worker import OutputPin, EditPin
        pin = self.reactor()._pins[pinname]
        assert isinstance(pin, (OutputPin, EditPin))
        if not isinstance(pin, EditPin):
            assert not preliminary
            if not self.executing:
                msg = "%s can set outputpin '%s' only while executing"
                raise Exception(msg % (self.reactor(), pinname))
        self.manager().set_reactor_result(self, pinname, value)

    def clear(self):
        #print("CLEAR")
        self.namespace.clear()
        self.PINS = PINS()
        for code in "code_start", "code_update", "code_stop":
            setattr(self, code, None)
