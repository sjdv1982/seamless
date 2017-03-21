Seamless was created on June 3rd, 2016

TODO:

Technically-oriented releases are marked with *

*0.1
- Javascript bridge with websockets
- Final decision on primitive names
- Overhaul dtypes, docson/type registration API
- Signals, OpenGL rendering
- Demos: OpenGL, plotly, orca?

*0.2
- Binary (struct) cells, active switches
- Silk: managing variable-length arrays with allocators (subclass ndarray), C header registrar
- C interop
- Game of Life demo with Cython and C
- Update OpenGL demo

0.3
- dictpins (behaves as dynamic dict-of-pins with each pin of the same type)
- multipins (composite pin, may include dictpin)
- Finalize context graph format and their names, update tofile/fromfile accordingly
- Finalize resource management
- Finalize basic API, also how to change macros
- Update demos

*0.4
- Thread reactors, process reactors
- Synchronous transformers, process transformers

0.5
- Docson/type registration API and hook GUI
- Error message hook API and GUI (also for pending inputs)
- Set up user library directory and robogit
- Update demos

*0.6
- Array cells, channels, caching, sub-cells
- GPU computing (OpenCL)
- Update Game of Life demo

0.7
- Hook API and GUI for cell creation
- Update demos

0.8
- ATC, fold/unfold switches, Silk GUI generation, Silk mvcc hooked up with error message hook API
- More demos (tetris?)

*0.9
- Debugging, code editor (WIP)

*0.10
- Collaborative protocol, context forking (code parallelization/delegated computing)

*1.0
- Lazy evaluation, GPU-GPU triggering
