Technically-oriented releases are marked with *

\*0.1
After release, make videos:
  Basic example, based on examples/basic.py, then examples/basic-macro.py
  Fireworks
  3D
  Docking
  Orca (don't show the code)

0.2

- macros
I am not quite happy with how macros are being used. The direct import method
(defined macro "spam" in "eggs.py", "from eggs import spam") is fine for the
core macros, but it hampers live programming on other macros (though it isn't
prevented completely ; see test-dynamic-macro.py for an API example),
since it prohibits the link between macro <=> cell <=> file.
To solve that, a function .load_macro("spam", "eggs.py") is needed, that creates
a macro with a .cell attribute, with .cell.resource.filepath
(and .resource.lib) set properly. The .cell can be link()'ed as usual.
In addition, the function .load_block_macro("ham", "ham.py") loads ham.py as a
code block, i.e. adding "@macro", a def, and indenting the code.
ham.py can thus be a main script, like the ones in tests and examples.
For all main scripts in tests and examples, the "ctx = " and ctx.tofile
must be made conditional on __name__ == "__main__"

- Replace the use of killable threads with processes... gives a problem with Orca example (fixed now ?), docking example (?), see Github issue
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
- Binary (struct) cells, implemented as structured "array" cells with dtype/shape/ndim (with functionality similarly to composite cells)
- Active switches (connection level; workers don't see it, except that pin becomes undefined/changes value)
- Silk: managing variable-length arrays with allocators (subclass ndarray), C header registrar, fix Bool default value bug + bug in examples/silk/test.py
- Document Silk, make it an official (supported) part of seamless
- C interop
- Game of Life demo with Cython and C
- Update OpenGL demos

0.4
- Finalize context graph format and their names, update tofile/fromfile accordingly
- Finalize resource management
- Finalize basic API, also how to change macros (SEE ABOVE)
- Cleanup code layout
- Document tofile/fromfile, saving options and seamless file format
- Code documentation + dtype/worker documentation system
- Set up user library directory and robogit
- Update demos

\*0.5
- Thread reactors, process reactors
- Synchronous transformers (do we need this?)
- Process transformers (now that execution is in a process, do we need this??)
- Cell arrays, channels, GUI-widget cells
- GPU computing (OpenCL)
- Update Game of Life demo

0.6
- Hook API and GUI for cell creation
- Update demos

0.7
- ATC, fold/unfold switches, Silk GUI generation
- More demos (tetris?)

\*0.8
- Python debugging, code editor (WIP)

\*0.9
- Collaborative protocol / delegated computing

\*1.0
- Lazy evaluation, GPU-GPU triggering
