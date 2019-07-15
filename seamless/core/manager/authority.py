import weakref

class AuthorityManager:
    def __init__(self, manager):
        self.manager = weakref.ref(manager)

    def check_modified_paths(self, modified_paths, authority_mode):
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