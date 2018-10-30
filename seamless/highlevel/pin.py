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
    def transfer_mode(self):
        hpin = self._get_hpin()
        return hpin["transfer_mode"]
    @transfer_mode.setter
    def transfer_mode(self, value):
        #TODO: validation
        hpin = self._get_hpin()
        hpin["transfer_mode"] = value
        self._parent()._parent()._translate()

    @property
    def access_mode(self):
        hpin = self._get_hpin()
        return hpin["access_mode"]
    @access_mode.setter
    def access_mode(self, value):
        #TODO: validation
        hpin = self._get_hpin()
        hpin["access_mode"] = value
        self._parent()._parent()._translate()

    @property
    def content_type(self):
        hpin = self._get_hpin()
        return hpin["content_type"]
    @content_type.setter
    def content_type(self, value):
        #TODO: validation
        hpin = self._get_hpin()
        hpin["content_type"] = value
        self._parent()._parent()._translate()


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

    def __dir__(self):
        hpins = self._get_hpins()
        return hpins.keys()
