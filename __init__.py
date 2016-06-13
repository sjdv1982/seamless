"""
Seamless: framework for data-driven and live programming
Copyright 2016, Sjoerd de Vries

- Organizes code and structured data into cells. Cells can be organized into cell chains. A Jupyter notebook would be an example of a cell chain.
  Cells work similar as in Jupyter, but there are three important differences:
    *   There are many single cells that are not organized into cell chains.
    *   Every cell and cell chain has its own process (with a REPL, if possible)
        Seamless is based on communication between cell(-chain)-based processes.
        By default, processes are IPython kernels, but they can be anything that understand seamless messages (and Jupyter messages, if there is a REPL)
    *   There are no input and output cells. Instead, there are data cells and code cells.
        For data cells, any type of structured data (XML, JSON, Numpy, Spyder) is understood.
        Code cells currently means Python code, but other languages (e.g. Javascript, Julia) could eventually be supported as well
        Both data cells and code cells can be connected (as input and/or output) to cell transformers and visualizers
    *   Cell chains are typically based on the source code file of a script plus a (manual) definition of cell borders.
        For now, cells consist of one or more lines, and every line belongs to one cell.
        In a cell chain, cells are not executed one by one. Instead, you can (manually) define which cells depend on which prior cells.
        If you (re-)execute a cell, all of its depencies are (re-)executed as well (if they have changed).
        Unlike Jupyter cells, this gives the same effect as executing the program from start.
        File dependencies, dependencies on cells outside the cell chain, and Spyder dependencies (see below) can also be defined
    *   Cell chains can also be virtual (not backed up by a file; some cells being links into cells in other cell chains )
        This allows you to set up testing versions or visualization versions of a script, that automatically update when the script updates
- Spyder (TODO)
- ATC (TODO)
- RaeDae (TODO)
- Lightweight OpenGL(TODO)
- Topview (TODO)
- File-based pipeline (TODO)

Cell are always contained inside a cell manager, but the connections are in principle cell-cell
Cells can be managed authoritatively, meaning that their state is stored.
  When seamless is reloaded, non-authoritative cells get auto-generated from the authoritative ones.
  Attempts to update authoritative cells during reload will be ignored
Cell-cell connections can be input and/or output (read and/or write)

A special manager is the incremental cell manager. It is always contains three connections.
All three connections have the same datatype X for both input and output.
One connection is the source (R+W), the second is the increment (R+W), and the third is the output (R).
The incremental manager contains two private, authoritative cell, the replica and the output cell.
In the non-error state, the output cell is equal to the increment
In the error state, it is equal to the source
Whenever the manager receives a source update, it enters the error state
It remains in the error state unless the replica becomes equal to the source,
 or the source becomes equal to the increment
The manager accepts three signals:
- Update source: sets the source equal to the increment
- Reset increment: the increment and the replica become equal to the source
- Ignore: the replica becomes equal to the source

"""


#Mode variables: these change dynamically

"""
Are we in explicit mode? ATC chains operate differently:
- If we are in explicit mode, create a cell with a separate process or every ATC operation in the chain.
  Operation failures (exceptions) will be, via the Jupyter protocol, sent to consoles attached to the cells
  If a particular operation does not fail, it will send its result back to us.
  Our ATC manager will send the result to the next cell
- If we are not in explicit mode, the entire ATC is carried out by us (i.e. in the current process).
  Any exception will cause us to abort:
    if we are the main process, that's the end of it all, unless the exception gets caught
    if we are ourselves inside a cell process, we will be free to receive new commands; it is assumed that the failed chain did nothing


"""
_explicit = []
def explicit():
    try:
        return _explicit[-1]
    except IndexError:
        return False
def push_explicit(new_explicit):
    assert new_explicit in (True, False), new_explicit
    _explicit.append(new_explicit)
def pop_explicit():
    _explicit.pop()




#State variables: these are defined once before init(). Changing them later will not work

master = True
"""
Are we the master process?
"""

sf_process = None
"""
OS/ZeroMQ process/port number for the seamless feedback (SF) handler process.
Must be defined if we are not master, and only then
"""

master_process = None
"""
OS/ZeroMQ process/port number for the master process. May be defined only if we are not master.
Allows direct communication with the master process, without mediation by the SF handler
"""

sf_port = None
"""
Our SF port name, how we identify ourselves to the SF process (and the master process, if defined).
Must be defined if we are not master, and only then
"""

master_sf_port = None
"""
SF port name for the master process (default: same as sf_port)
May be defined only if master_process is defined
"""

live = False
"""
Are we part of a seamless live system? If not, we don't have to send any messages
"""

visual = False
_allowed_visual = [False, "qt", "remote"]
"""
Can we deal with cell visualization requests?
For now, three values for are allowed:
    False: no cell visualization of any kind, silently ignore all requests
    "qt": create a Qt visualizer
    "remote": forward all visualization
"""

_init = False

#The modules cannot yet access the seamless state variables
from . import atc, spyder, gui, process, sf, cellmanagers, transformers, datatypes

def init():
    global _init
    global master, _master
    global sf_process, _sf_process
    global master_process, _master_process
    global sf_port, _sf_port
    global master_sf_port, _master_sf_port
    global live, _live, visual, _visual

    #verify that our state is sane
    if master:
        assert sf_process is None
        assert master_process is None
        assert sf_port is None
        assert master_sf_port is None
    else:
        assert sf_process is not None
        assert sf_port is not None
        if not master_process:
            assert master_sf_port is None

    if visual not in _allowed_visual:
        raise ValueError("'visual' must be in {0}, not {1}".format(_allowed_visual, visual))
    if visual != False:
        assert live == True

    #bake it in; don't allow submodules (or anything else) to accidentally change it
    _master = master
    del master
    _sf_process = sf_process
    del sf_process
    _master_process = master_process
    del master_process
    _sf_port = sf_port
    del sf_port
    _master_sf_port = master_sf_port
    del master_sf_port
    _live, _visual = live, visual
    del live, visual
    _init = True

    #now we tell submodules about the state
    atc.init()
    spyder.init()
    gui.init()
    process.init()
    cellmanagers.init()

    def master():
        return _master

    def sf_process():
        return _sf_process

    def master_process():
        return _master_process

    def sf_port():
        return _sf_port

    def master_sf_port():
        return _master_sf_port

    def live():
        return _live

    def visual():
        return _visual
