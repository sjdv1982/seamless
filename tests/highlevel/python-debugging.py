"""
EXPERIENCES IN DEBUGGING PYTHON TRANSFORMERS
============================================
1. The transformer must be in a thread; a process will not work
2. When the transformer code invokes the debugger, Seamless cannot be run in Jupyter
   but pdb/ipdb work when invoked *directly* from a Jupyter cell (i.e. not a transformer)
3. All debuggers (pdb, ipdb and pdb-clone) require the transformer to be run
  as a thread, except ForkedPdb, which runs fine as thread or as process
4. Seamless *can* be run in IPython, but the debugger and IPython compete for keystrokes,
   so the result is not pleasant. Before the script ends, there is no problem
5. All debuggers work well if Seamless is run with Python
   However, ipdb gives an error message on exit (SQLite programming error)
   In addition, ipb does not like to be killed, so don't change the
    transformer source while ipdb is running

Conclusion:
- ForkedPdb is the best; added to Seamless as seamless.pdb
- In Jupyter, transformer code must be copy-pasted into a Jupyter cell and then
  be debugged non-reactively.
  Alternatively, the notebook can be converted to .py, with seamless.mainloop()
   appended, and then run in Python. The mounted cells can then be edited
   reactively using a text editor.

Finally, it is possible to use a headless debugger that connects to an IDE
I have studied ptvsd, for Visual Studio Code, which can be installed as a Python module.
It is easy enough to let enable ptvsd attachment:
(The default hostname is 0.0.0.0, and the default port is 5678;
these can be overridden by passing a (host, port) tuple as the first argument
of enable_attach() ).

import ptvsd
ptvsd.enable_attach()
ptvsd.wait_for_attach()  # blocks execution until debugger is attached

NOTE: it is extremely annoying that all debuggers use breakpoints based on file names.
Fortunately, this is easy to spoof for Python.
Internally, ptvsd uses code from PyDev to debug the script. It relies on
inspect.currentframe().f_code.co_filename to find the filename
(although mappings can be defined).
This corresponds *exactly* to the identifier of seamless.core.cached_compile.
TODO: Therefore, a "virtual filename" attribute will be supported, which will be passed
 to cached_compile. It is your responsibility that this corresponds to a real file.
TODO: interpreted modules will also have a file path in their tree. You can map
 to their write-only, just as for binary modules, to facilitate visual debugging.
File names and paths must be stripped from checksum calculations.

"""
from seamless.highlevel import Context

ctx = Context()
ctx.a = 12


def triple_it(a):
    import sys, pdb
    class ForkedPdb(pdb.Pdb):
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

    #from pdb_clone.pdb import set_trace
    #from pdb import set_trace
    #from ipdb import set_trace
    #set_trace = ForkedPdb().set_trace
    from seamless.pdb import set_trace
    set_trace()
    return 3 * a

ctx.transform = triple_it
ctx.transform.debug = True
ctx.code >> ctx.transform.code
ctx.code.mount("triple_it.py")
ctx.transform.a = ctx.a
ctx.myresult = ctx.transform
ctx.compute(report=None)
print(ctx.myresult.value)