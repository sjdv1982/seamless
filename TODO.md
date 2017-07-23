Technically-oriented releases are marked with *

\*0.1
- Basic documentation:
  - In README.md:
    - fix the format (.md)
- Short README.txt for each of the examples:
    - plotly (DONE)
    - OpenGL fireworks (DONE)
    - docking (2 examples)
    - OpenGL 3D
- Make zips for the examples and tests
- Set up gitpage for sphinx documentation
- Fix documentation links in README.md, sphinx/examples.rst (also for zips)
- Make PyPI package

After release, make videos:
  Basic example, based on examples/basic.py, then examples/basic-macro.py
  Fireworks
  3D
  Docking
  Orca (don't show the code)

0.2
- Replace the use of killable threads with processes... gives a problem with Orca example (fixed now ?)
- Replace ctx.CHILDREN, ctx.CELLS etc. with ctx.self.children, ctx.self.cells, etc.
- Get rid of seamless.qt
- Composite (JSON) cells
- Expand and document seamless shell language (slash)
- Logging + dtype/worker documentation.resource system (using composite cells)
- Error message logging system (using composite cells)
- Overhaul dtypes, docson/type registration API, integrate with logging/documentation system. "array" and "json" are no longer dtypes, but formats
- Update demos

\*0.3
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

\*0.5
- Thread reactors, process reactors
- Synchronous transformers (do we need this?)
- Process transformers (now that execution is in a process, do we need this??)

\*0.6
- Cell arrays, channels, GUI-widget cells
- GPU computing (OpenCL)
- Update Game of Life demo

0.7
- Hook API and GUI for cell creation
- Update demos

0.8
- ATC, fold/unfold switches, Silk GUI generation
- More demos (tetris?)

\*0.9
- Python debugging, code editor (WIP)

\*0.10
- Collaborative protocol / delegated computing

\*1.0
- Lazy evaluation, GPU-GPU triggering
