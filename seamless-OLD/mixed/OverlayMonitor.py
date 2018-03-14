from .MakeParentMonitor import MakeParentMonitor

def warn(s):
    print("WARNING:", s)

class OverlayMonitor(MakeParentMonitor):
    """A subclass of Monitor where some paths can be fixed by inchannels

    When an inchannel is opened, and a message is received, the path is set
     with the message value. The first received message causes the inchannel
     to become *authoritative*. When the path or a parent/child path is changed via
     API, what happens is determined by policy. (There are two policies, for
     path and parent/child path)
    Policies:
    1. Exception
    2. Rejected with warning (Only for the inchannels; other path components are accepted)
    3. Accepted with warning
    4. Accepted, and inchannel gets removed (with warning)
    5. Accepted, and inchannel gets removed (without warning)
    Default policy is 5. for path, and 2. for parent path
    Deleting paths via API always succeeds; it prints a warning if policy 1-4
    Adding inchannels *always* removes path and parent/child inchannels, with warning
    """
    policy_path = 5
    policy_parent_child_path = 2
    def __init__(self, data, storage, form, inchannels):
        self.inchannels = inchannels #dict of (path, authoritative)
        super().__init__(data, storage, form)

    def add_inchannel(self, path):
        assert isinstance(path, tuple), path
        if path in self.inchannels:
            self.inchannels[path] = False
            return
        l0 = len(path)
        for cpath in list(self.inchannels.keys()):
            breaking = False
            l1 = len(cpath)
            if l1 <= l0:
                if path[:l1] == cpath:
                    breaking = True
            else:
                if cpath[:l0] == path:
                    breaking = True
            if breaking:
                warn("Disconnecting inchannel %s" % path)
                self.inchannels.pop(cpath)
        self.inchannels[path] = False

    def receive_inchannel_value(self, path, value):
        assert path in self.inchannels, path
        super().set_path(path, value)
        self.inchannels[path] = True

    def _check_policy(self, path, p, authoritative, deletion):
        if deletion:
            if p in (1,2,3,4):
                warn("inchannel %s exists, disconnected" % path)
                self.inchannels.pop(path)
            elif p == 5:
                self.inchannels.pop(path)
            else:
                raise ValueError(p)
            return True

        if p == 1:
            raise Exception(path) #inchannel exists
        elif p == 2:
            if authoritative:
                warn("inchannel %s exists, update rejected" % path)
                return False
            else:
                return True
        elif p == 3:
            if authoritative:
                warn("inchannel %s exists, value overwritten" % path)
            return True
        elif p == 4:
            warn("inchannel %s exists, disconnected" % path)
            self.inchannels.pop(path)
            return True
        elif p == 5:
            self.inchannels.pop(path)
            return True
        else:
            raise ValueError(p)

    def _check_inchannels(self, path, *, deletion):
        if path in self.inchannels:
            authoritative = self.inchannels[path]
            return self._check_policy(path, self.policy_path, authoritative, deletion)
        else:
            l0 = len(path)
            p = self.policy_parent_child_path
            for cpath in list(self.inchannels.keys()):
                exists = False
                l1 = len(cpath)
                if l1 <= l0:
                    if path[:l1] == cpath:
                        exists = True
                else:
                    if cpath[:l0] == path:
                        exists = True
                if exists:
                    authoritative = self.inchannels[cpath]
                    result = self._check_policy(path, p, authoritative, deletion)
                    if not result:
                        return False
            return True

    def set_path(self, path, subdata):
        if not self._check_inchannels(path, deletion=False):
            return
        super().set_path(path, subdata)

    def insert_path(self, path, subdata):
        if not self._check_inchannels(path, deletion=False):
            return
        super().insert_path(path, subdata)

    def del_path(self, path):
        if not self._check_inchannels(path, deletion=True):
            return
        super().del_path(path)

#TODO: a subclass/mixin for forward signaling to outchannels
# outchannel signaling must be buffered on the outside, because validation comes first!!
