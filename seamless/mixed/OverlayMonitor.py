from .MakeParentMonitor import MakeParentMonitor

def warn(s):
    print("WARNING:", s)

class OverlayMonitor(MakeParentMonitor):
    """A subclass of Monitor where some paths can be fixed by inchannels,
       and where some path updates are listened to and forwarded in the form
       of outchannels
       inchannels: list of inchannel paths
       outchannels: dict of outchannel hooks (path => callable)

       For now, outchannel hooks exceptions are not caught
    """
    def __init__(self,
      data, storage, form, inchannels, outchannels, *,
      plain=False, **args
    ):
        self.inchannels = set()
        self.outchannels = outchannels
        super().__init__(data, storage, form, plain=plain, **args)
        for path in inchannels:
            self._add_inchannel(path)

    def _add_inchannel(self, path):
        assert isinstance(path, tuple), path
        if path in self.inchannels:
            return
        l0 = len(path)
        for cpath in self.inchannels:
            breaking = False
            l1 = len(cpath)
            if l1 <= l0:
                if path[:l1] == cpath:
                    breaking = True
            else:
                if cpath[:l0] == path:
                    breaking = True
            if breaking:
                raise Exception("Overlapping paths: %s and %s" % (cpath, path))
        self.inchannels.add(path)

    def receive_inchannel_value(self, path, value):
        assert path in self.inchannels, path
        super().set_path(path, value)
        self._update_outchannels(path)

    def _check_inchannels(self, path):
        if path in self.inchannels:
            warn("inchannel %s exists, value overwritten" % path)
        else:
            l0 = len(path)
            for cpath in self.inchannels:
                exists = False
                l1 = len(cpath)
                if l1 <= l0:
                    if path[:l1] == cpath:
                        exists = True
                else:
                    if cpath[:l0] == path:
                        exists = True
                if exists:
                    warn("inchannel %s exists, value overwritten" % path)
                    break

    def _update_outchannels(self, path):
        for outpath, func in self.outchannels.items():
            if path[:len(outpath)] == outpath:
                data = self.get_path(outpath)
                func(data.value)

    def set_path(self, path, subdata):
        self._check_inchannels(path)
        super().set_path(path, subdata)
        self._update_outchannels(path)

    def insert_path(self, path, subdata):
        self._check_inchannels(path)
        super().insert_path(path, subdata)
        self._update_outchannels(path)

    def del_path(self, path):
        self._check_inchannels(path)
        super().del_path(path)
        self._update_outchannels(path)
