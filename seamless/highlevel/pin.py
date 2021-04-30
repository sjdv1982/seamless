# TODO: add validation for io, celltype, must_be_defined; both as attributes (double PinWrapper) and as dict

from weakref import ref

class PinWrapper:
    def __init__(self, parent, pinname):
        self._parent = ref(parent)
        self._pinname = pinname

    def _get_hpin(self):
        from .Transformer import Transformer
        from .Macro import Macro
        parent = self._parent()
        if isinstance(parent, Transformer):
            h = parent._get_htf()
        elif isinstance(parent, Macro):
            h = parent._get_node()
        else:
            raise TypeError(parent)
        return h["pins"][self._pinname]


    @property
    def celltype(self):
        if self._pinname == "code":
            return "code"
        hpin = self._get_hpin()
        return hpin["celltype"]
    @celltype.setter
    def celltype(self, value):
        if self._pinname == "code":
            raise AttributeError
        #TODO: validation
        hpin = self._get_hpin()
        hpin["celltype"] = value
        self._parent()._parent()._translate()

    @property
    def subcelltype(self):
        if self._pinname == "code":
            return "code"
        hpin = self._get_hpin()
        return hpin.get("subcelltype")
    @subcelltype.setter
    def subcelltype(self, value):
        if self._pinname == "code":
            raise AttributeError
        #TODO: validation
        hpin = self._get_hpin()
        hpin["subcelltype"] = value
        self._parent()._parent()._translate()

    @property
    def io(self):
        if self._pinname == "code":
            return "input"
        from .Transformer import Transformer
        from .Macro import Macro
        parent = self._parent()
        if isinstance(parent, Transformer):
            return "input"
        hpin = self._get_hpin()
        return hpin["io"]

    @io.setter
    def io(self, value):
        if self._pinname == "code":
            raise AttributeError
        from .Transformer import Transformer
        from .Macro import Macro
        parent = self._parent()
        if isinstance(parent, Transformer):
            assert value == "input", value
        elif isinstance(parent, Macro):
            assert value in ("input", "output", "parameter"), value
        else:
            raise TypeError(parent)
        #TODO: more validation
        hpin = self._get_hpin()
        hpin["io"] = value
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
        from .Macro import Macro
        parent = self._parent()
        if isinstance(parent, Transformer):
            h = parent._get_htf()
        elif isinstance(parent, Macro):
            h = parent._get_node()
        else:
            raise TypeError(parent)
        return h["pins"]

    def __getattr__(self, pinname):
        if pinname.startswith("_"):
            raise AttributeError(pinname)
        if pinname == "code":
            return PinWrapper(self._parent(), "code")
        hpins = self._get_hpins()
        if pinname not in hpins:
            raise AttributeError(pinname)
        return PinWrapper(self._parent(), pinname)


    def __setattr__(self, pinname, value):
        from .Transformer import default_pin
        if pinname.startswith("_"):
            return super().__setattr__(pinname, value)
        if pinname == "code":
            raise AttributeError(pinname)
        hpins = self._get_hpins()
        if value is None:
            return self.__delattr__(pinname)
        if isinstance(value, PinWrapper):
            pin = value._get_hpin()
            hpins[pinname] = pin
        elif value == {}:
            hpins[pinname] = default_pin.copy()
        elif isinstance(value, dict):
            hpins[pinname] = value.copy()
        else:
            raise TypeError(pinname)

    def __getitem__(self, pinname):
        return getattr(self, pinname)

    def __setitem__(self, pinname, value):
        return setattr(self, pinname, value)

    def __delattr__(self, pinname):
        if pinname == "code":
            raise AttributeError(pinname)
        hpins = self._get_hpins()
        if pinname in hpins:
            hpins.pop(pinname)
            parent = self._parent()
            subpath = (*parent._path, pinname)
            ctx = parent._get_top_parent()
            ctx._destroy_path(subpath)
            ctx._translate()

    def __str__(self):
        return "Pins of " + str(self._parent())

    def __repr__(self):
        return str(self)

    def __iter__(self):
        hpins = self._get_hpins()
        return iter(hpins)

    def __dir__(self):
        hpins = self._get_hpins()
        return sorted(list(hpins.keys()) + ["code"])
