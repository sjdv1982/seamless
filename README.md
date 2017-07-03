Seamless: a cell-based reactive programming framework
Seamless was created on June 3rd, 2016

Requirements: Python 3.5+, PyQt5 (including QWebEngine), numpy, PyOpenGL, cson
Recommended: scipy, pandas, websockets
NOTE: Seamless scripts are meant to be executed within IPython

The nine seamless constructs (sorted from good to ugly):
1. context
2. cell
3. transformer
4. pin
5. reactor
6. macro
7. export
8. registrar
9. observer

Seamless Zen

Watch the state as it is now, don't watch the news.
All state is in cells, unless it is local.
Always be prepared to rebuild from cells.
Cells are good, files are bad.
Importing external libraries is good, importing project code is bad.
Namespaces are good, classes less so.
GUIs are good, unless they hide the state.
Edit all state, then edit the editor
Code execution is repeatable; if it is not repeatable, you throw away the code, and keep its result.
Transform lazily, react eagerly.


TODO:

Technically-oriented releases are marked with *

*0.1
- Basic documentation:
  - In README.md:
    - a short summary
    - a reference to help(...) for each construct
    - a short example, and a link to the examples directory + zip file / test directory
    - fix the format (.md)
- Short documentation for each of the demos:
    - plotly
    - OpenGL fireworks
    - docking (2 examples)
    - OpenGL 3D
- Make PyPI package

After release, make videos:
  Basic example: consensus between test-editor and test-editor-lib, then macro
  Fireworks
  3D
  Docking
  Orca (add example code back in)

0.2
- Replace the use of killable threads with processes... gives a problem with Orca example
- Replace ctx.CHILDREN, ctx.CELLS etc. with ctx.self.children, ctx.self.cells, etc.
- Get rid of seamless.qt
- Composite (JSON) cells
- Expand and document seamless shell language (slash)
- Logging + dtype/worker documentation.resource system (using composite cells)
- Error message logging system (using composite cells)
- Overhaul dtypes, docson/type registration API, integrate with logging/documentation system. "array" and "json" are no longer dtypes, but formats
- Update demos

*0.3
- Multiple code cells in transformers/reactors
- Preliminary outputpins (in transformers [as secondary output] and in reactors)
- Preliminary inputpins (pins that accept preliminary values). Right now, all inputpins are preliminary!
- Address shell() memory leak: IPython references may hold onto large amounts of data
- Address GLstore memory leak: stores may not be freed (?)
- Binary (struct) cells, implemented as "array" cells with dtype/shape/ndim
- Active switches (connection level; workers don't see it, except that pin becomes undefined/changes value)
- Silk: managing variable-length arrays with allocators (subclass ndarray), C header registrar, fix Bool default value bug + bug in examples/silk/test.py
- Document Silk
- C interop
- Game of Life demo with Cython and C
- Update OpenGL demos

0.4
- Finalize context graph format and their names, update tofile/fromfile accordingly
- Finalize resource management
- Finalize basic API, also how to change macros
- Cleanup code layout
- Document tofile/fromfile, saving options and seamless file format
- Code documentation + dtype/worker documentation system
- Set up user library directory and robogit
- Update demos

*0.5
- Thread reactors, process reactors
- Synchronous transformers (do we need this?)
- Process transformers (now that execution is in a process, do we need this??)

*0.6
- Cell arrays, channels, GUI-widget cells
- GPU computing (OpenCL)
- Update Game of Life demo

0.7
- Hook API and GUI for cell creation
- Update demos

0.8
- ATC, fold/unfold switches, Silk GUI generation
- More demos (tetris?)

*0.9
- Python debugging, code editor (WIP)

*0.10
- Collaborative protocol / delegated computing

*1.0
- Lazy evaluation, GPU-GPU triggering
