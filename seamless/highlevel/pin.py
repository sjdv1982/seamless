from weakref import ref

class InputPin:
    pass

class OutputPin:
    _virtual_path = None
    def __init__(self, parent, worker, path):
        pass

class InputPinWrapper:
    def __init__(self, parent, pinname):
        self._parent = ref(parent)
        self._pinname = pinname

    def _get_hpin(self):
        from .Transformer import Transformer
        from .Reactor import Reactor
        parent = self._parent()
        if isinstance(parent, Transformer):
            h = parent._get_htf()
        elif isinstance(parent, Reactor):
            h = parent._get_hrc()
        else:
            raise TypeError(parent)
        return h["pins"][self._pinname]


    @property
    def celltype(self):
        hpin = self._get_hpin()
        return hpin["celltype"]
    @celltype.setter
    def celltype(self, value):
        #TODO: validation
        hpin = self._get_hpin()
        hpin["celltype"] = value
        self._parent()._parent()._translate()

    def __getitem__(self, pinname):
        return getattr(self, pinname)

    def __setitem__(self, pinname, value):
        return setattr(self, pinname, value)

class PinsWrapper:
    def __init__(self, parent):
        self._parent = ref(parent)

    def _get_hpins(self):
        from .Transformer import Transformer
        from .Reactor import Reactor
        parent = self._parent()
        if isinstance(parent, Transformer):
            h = parent._get_htf()
        elif isinstance(parent, Reactor):
            h = parent._get_hrc()
        else:
            raise TypeError(parent)
        return h["pins"]

    def __getattr__(self, pinname):
        hpins = self._get_hpins()
        if pinname not in hpins:
            raise AttributeError(pinname)
        pin = hpins[pinname]
        io = pin.get("io", "input")
        if io == "input":
            kls = InputPinWrapper
        else:
            raise NotImplementedError(io)
        return kls(self._parent(), pinname)

    def __getitem__(self, pinname):
        return getattr(self, pinname)

    def __setitem__(self, pinname, value):
        return setattr(self, pinname, value)

    def __str__(self):
        return str(self._get_hpins())

    def __dir__(self):
        hpins = self._get_hpins()
        return hpins.keys()
