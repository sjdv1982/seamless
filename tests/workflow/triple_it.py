def triple_it(a):
    import sys, pdb

    class ForkedPdb(pdb.Pdb):
        """A Pdb subclass that may be used
        from a forked multiprocessing child

        """

        def interaction(self, *args, **kwargs):
            _stdin = sys.stdin
            try:
                sys.stdin = open("/dev/stdin")
                super().interaction(*args, **kwargs)
            finally:
                sys.stdin = _stdin

    # from pdb_clone.pdb import set_trace
    # from pdb import set_trace
    # from ipdb import set_trace
    # set_trace = ForkedPdb().set_trace
    from seamless.pdb import set_trace

    set_trace()
    return 3 * a
