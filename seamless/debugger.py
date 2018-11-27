#from https://stackoverflow.com/a/23654936
import sys, pdb as pdb_ORIGINAL
class ForkedPdb(pdb_ORIGINAL.Pdb):
    """A Pdb subclass that may be used
    from a forked multiprocessing child

    """
    def interaction(self, *args, **kwargs):
        _stdin = sys.stdin
        try:
            sys.stdin = open('/dev/stdin')
            super().interaction(*args, **kwargs)
        finally:
            sys.stdin = _stdin

import imp
_pdb = ForkedPdb()
pdb = imp.new_module("seamless.pdb")
sys.modules["seamless.pdb"] = pdb
for k in dir(pdb_ORIGINAL):
    if hasattr(_pdb, k):
        setattr(pdb, k, getattr(_pdb, k))
