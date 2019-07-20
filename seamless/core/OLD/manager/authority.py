import weakref
from weakref import WeakKeyDictionary

class AuthorityManager:        
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.authority = WeakKeyDictionary()

    def register_cell_paths(self, cell, inpaths, outedpaths):
        assert cell not in self.authority
        if not cell._monitor:
            return
        self.authority[cell] = {}
        for outpath in outedpaths:
            #(determine if outchannel has at least partial authority)
            raise NotImplementedError
    """
    #TODO
    def on_inconnect(cell):
        cell must be a Cell, change valuecache refs from auth to non-auth
        StructuredCells have static auth!
    """

    def verify_modified_paths(self, cell, modified_paths, authority_mode):
        raise NotImplementedError # livegraph branch
        """
        Invoked by StructuredCell backend to check if path modifications are allowed.
        If authority mode:
            Check that all paths have full authority.            
            The top path has full authority if there are no inchannels.
            All other paths have full authority if no inchannel is a subpath of it, 
             nor are they a subpath of any inchannel
        else:
            Check that all paths have no authority.
            Each path must be a subpath of an inchannel.
        If the test fails, raise an Exception
        """

from ..cell import Cell
from ..structured_cell import StructuredCell
