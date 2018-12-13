NOTE: Seamless runs very well with Jupyter, but requires tornado-4.5.3, not tornado 5.1!

Great Refactor is underway (see seamless-towards-02.md).

Part 1 is now complete
Most of the high level is done.

Things to do:

Part 2: high level

A: get BCsearch working
(initial/demo version works now)
- Follow roadmap (see BCsearch directory)
- Network evaluation:
  Almost done (tests/simple-remote-client/server)
  TODO:
  - embed in a real network server (and support it as .server, not just file://)
    UPDATE: this should be done by having a special GRAPH namespace on the REST server;
    the highlevel may share contexts (TODO) and transformers in this manner; sharing
    will expose the context/transformer to receive GRAPH commands; in a separate mechanism,
    a transformer/context can be configured in "delegated mode", meaning that local computation
    is disabled and that there must be either a cache hit or a worker that takes GRAPH commands)
  - send back the response (RPSEAMLESS?)
  - implement pin/manager.send_update_from_remote() that accepts the response
    and dispatches it towards the various cell types
  - make sure that a remote job_transformer loses equilibrium when a new result celltype
     is connected (changes output signature)
- Services proof-of-principle
  Low-level services (non-interactive transformer)

intermezzo:
- convert "json" to "plain" everywhere (JsonCell etc).
- Look into "gracefully shutting down transformers"; slows things down,
   but proper caching may rely on it?
   UPDATE: for now, needs to have USE_PROCESSES is True,
    else causes segfault for BCSearch/test.py
- re-run all tests

B: Towards a first real example
- Constructors, finish testing
  Test library-containing-another-library    
  Make sure constructors work correctly when copying parent contexts
  Test indirect library update system, also with constructors
- Finish browser lib
-  First real example:
  - Convert topology.json (of a different ctx!) to SVG
  - Interject merge for manual edit
  - Hook up browser for visualization

C: Towards Camembert plots (big!)
- High-level:
  macros (by definition low-level) with language (python) and api (seamless.core) fields.
- Call graph serialization
- Port websocketserver and dynamic_html
- Integrate with Observable Notebook: https://beta.observablehq.com/@sjdv1982/model-view-controller
(see also architecture.txt)

D: Port the peptide trajectory editor, use Observable instead of Jupyter.

E: The final new features before the merge
  - Some more services proof-of-principle
    Low-level services (non-interactive transformer) will have been done
    Other possible services: interactive transformer, pure reactor (non-interactive or interactive)  
    NOTE: These are strictly core.manager concerns. Neither the workers nor
     the high-level has anything to do with it!

Part 3 (low-level / cleanup): Towards the merge
   - Add back in int/float/str/bool cells because they are so convenient.
     Their content type will be int/float/text/bool.
     Adapters will convert among them (e.g. int=>float) and between them and JSON/mixed/text.
     Supported access modes are JSON and text. Adapters will convert to Silk.
   - Allow a "wrapping mode" for high-level cells. With wrapping mode on, a cell
      tries to behave as much as possible as cell.value. Auto-wrapping can be
      enabled at the context level.
     (Must be stored in meta-data)
   - Implement old lib.gui.edit as a new library, with new editpin.
   - Terminology: context children can be private, in which case they are not in __dir__.
     By default, they are public. No more "export".
     This has nothing to do with services. Services determine private and public based on
     what connects into the serviced context.
   - Start with lib porting. Port Qt editors (including HTML), but no more seamless.qt
     Port all macros, but store the code in plain Python modules in lib, that register a library context
   - Bring back slash0
   - Jettison Plotly and OpenGL for now; re-target main focus of Seamless towards scientific computations for now
   - Cleanup tests. With direct mode, most low-level tests should work now? Other ones can be ported to high-level    
    - Tests involving OpenGL can be jettisoned for now
   - Cleanup of the code base, remove vestiges of 0.1 (except lib and tests).
   - Cleanup of the TODO and the documentation (put in limbo). Don't forget /docs/WIP!

Merge into master; end of the Great Refactor

Part 4:
- Set virtual filenames for (non-compiled) transformers. See tests/highlevel/python-debugging.py
- "Simple mode" translation of transformers and reactors (no structured_cell, no schema)
- High-level: pure contexts. Pure contexts have at least some public output cells and output pins.
  Only pure contexts are can have a grand computation result: the checksums of the public outputs are what is being
   stored as the result of the grand computation.
  Connections to private output cells/pins are not forbidden, but lead to a loss of purity (with a big warning),
   as does demanding their value from Python.
  Reactors and transformers can also be marked as pure (the high-level makes transformers pure by default).
  In both cases, all output pins are public.
  However, an ephemeral output prevents a worker from being pure. Pure contexts can't have ephemeral public outputs, either.
  If they maintain their purity, a pure object is an independent caching unit. A hit in the
  computation checksum server will avoid the pure object to be (re-)translated at all.
  Also for the purpose of low-level caching, pure objects are a single dependency unit (a "virtual transformer"),
   so the low-level must be informed.  
  UPDATE: better to consider everything as pure by default, unless a cell is marked as ephemeral and is connected
  to/from the outside directly.
- The New Way of execution management (see below).
 For now, never shut down any worker
- Finalize caching:
  - structured cells: outchannels have a get_path dependency on an inchannel
  - structured cells: calculate outchannel checksum (see remarks in source code)
  - re-enable caching for high level (test if simple.py works now)
  - low-level reactors: they give a cache hit not just if the value of all cells are the same, but also:
         - if the connection topology stays the same, and
         - the value of all three code cells stays the same
     In that case, the regeneration of the reactor essentially becomes an update() event  

Part 5:
  - Signals (will always be ephemeral) UPDATE: rip them, or rather, make them a special case of plugin-socket (see below). Probably delay this until long-term
  - Observers (subclass of OutputPinBase) (UPDATE: traitlet instead. DONE)
  - Fully port over 0.1 lib: from .py files to Seamless library context files
  - Fully port over 0.1 tests
  - Clean up all vestiges of 0.1
  - Update documentation
  - Seamless console scripts and installer

0.2 release
Documentation      
Make new videos:
  - Basic example
  - Something with C/C++
  - Something with web forms/interactive notebook (some elements of part 6)
  - Docking

Intermezzo:
Do a bit of code cleanup
Have a look at all Python files. Move in-code TODOs etc. to documentation
Make the beginning of dev documentation, create some Github issues perhaps.
Start to reorganize some code, rename some APIs, etc.
Perhaps a bit more formal unit tests
Have a look at what it would take to go to PEP8 compliance.


Part 6: "Towards flexible and cloud-compatible evaluation"
  (use shared authority plan)
- Build upon services proof-of-principle (cloudless)
- HMTL gen from schema (UPDATE: less essential now? maybe do slash0 first)
- Bidirectional cell web editing via Websocketserver (UPDATE: use shared authority instead)
- Implement all the checksum servers
- Docker integration

0.3 release
Documentation  
Make new videos:
  - Making web services

Part 7:
- High-level mounting is not quite satisfactory (redundant "translated" context)
- The high level should store all permanent state in the graph nodes,
    nothing in the class instances. This way, the user can add their own syntax
    to manipulate the graph. (highlevel.ctx.\_children should go as well).
- Auxiliary, ephemeral and execution cells (see below)
  apply ephemeral cells to slash0
  Expand and document seamless shell language (slash)
  Make a slash reproducable mode, where every file is pulled from the file system in advance.
  However, POSIX commands are whitelisted (exempt).
  Other files may be whitelisted, leading to explicit dependency registration.
  The "compiled" slash graph should not access the file system at all
  (One cannot forbid the code cells and pulled command lines to do so, but they aren't supposed to).    
 Fix it with seamless.compiler which uses RLocks, need to be multiprocess!
   (transformers can compile!)
 - Silk: make add_validator a schema method!
- Graph translation should be asynchronous and interruptible
  (check regularly for interruption signals)
- Start with report channels that catch error messages, cache hits/misses etc.
   Gradually make Seamless such that it never crashes, but reports everything
   Kernels should be killable from shell (deactivates manager too)
- "only_auth" option in mounting context, mounting only authority cells
   This should be on by default
- Silk: error messages, multi-lingual (use Python format() syntax, but with properties to fill in, i.e. "The value cannot be {a.x}". This is natively supported by Python. No magic in the style of {a.x+a.y}; define a property for that)

Release as 0.4

Part 8:
- Flesh out modules (see below). Allow native IPython workers, as well
- Blocks
- Streams
- Special constructs (see below)
- Foreign-language integration
  - Extends the C/C++/Fortran proof-of-principle
  - Support CUDA/OpenCL
  - Requires also a Silk extension (GPU storage, fixed-binary, see silk.md)
  - IPython (.ipy)/Cython magic is not (or barely) necessary, since IPython is natively supported by workers.
- Bring back OpenGL support (or first integration with Observable?)
- High-level extensions of serialization (e.g. take care of reporting, shells... Do we need this? or midlevel only?)
- Port over Orca and other examples
- Make new videos (or first integration with Observable?):
    - Fireworks
    - 3D
    - Docking
    - Orca (don't show the code)  

Release as 0.5

Medium-term:
- Add Pandas as a query engine. Querying in Pandas is fantastic (much better than numexpr).
  Usage is as simple as `from pandas.core.computation.eval import eval as pd_eval`, and then:
  `pd_eval("c < 108 and c > 102", global_dict={"c": arr["c"]})` where arr is a structured array.
  The Silk wrapper can be passed in as a resolver for even more ease of use.
  (Unfortunately, using DataFrames stinks...
  DataFrames are very opinionated about holding state, no way to let Silk hold it in a vanilla Numpy array.
  This is because Pandas *really* wants a 2D Numpy array, of dtype=object if needed).
  With this, there is absolutely no need to re-implement/re-invent a PDB selection language.
  PDB selection should be server-side, sent as a JSON object with atom indices to the browser,
   to be interpreted by NGL.


Long-term:
- Meta-schema for schema editing (jsonschema has it)
- GUI around report channels (to visualize) and around high-level context (to edit)
- An extra "table" celltype, for text (like awk or org-mode) or binary (like Pandas)
- Reconsider the restrictions on transformers and reactors. [Give transformers
  edit pins and cache pins, allow them to have reactor pin API => YAGNI?].
  At least in theory, allow transformers/reactors to declare as sync/async, and thread/process.
  In the same vein, transformers should be able to be declared as "immediate", which means:
  sync and activated during translation / macro construction.
  (Macros are also "immediate" workers already).
  This allows a macro to depend on an immediate transformer, to avoid async macros (= cache misses).
- Support more foreign languages: Julia, R, JavaScript. IPython magics, also have a look at python-bond
- Simplified implementations, with various levels of reduced interactivity
  1. Frozen libraries. Libcell becomes a kind of symlink.
  No direct low-level library update, but also no high-level depsgraph.
  This is the only simplification that affects the high level.
  Can be done with the current code base, using a "simple" flag.
  2. Frozen low-level macros. All cells on which low-level macros depend are frozen.
  3. Frozen code cells. The code cells of all transformers and reactors are frozen.
  Code cells are considered both at the high-level and at the low-level implementation,
  i.e. a C++ transformer has its C++ code frozen, as well as the Python code that
  implements the cffi interface.
  4. Everything frozen. The graph is considered as a single computation that should yield
  the designated result cells. No interactivity, authority never changes
  => editpins are also forbidden.
- Specialized client implementations for special constructs
- Reactor start and stop side effects (see below), and other policies involving
  the New Way.
- Set up user library directory and robogit

Very long-term:
- Use the report system for detailed timings. Use this for precise measurements where
  the seamless overhead is, and how much.
- Python debugging / code editor (WIP) (see seamless-towards-02.md)
- Full feature implementation of Silk, e.g. constructs (see silk.md)
- Other *host* implementations? JavaScript? Erlang? Elixir? Go?
- "Activate" overhaul, the "onion" of Python with statements make it slow.
  Test on Collatz test. This is a good test for the New Way and also for
  simplified implementations.  
- GPU-GPU triggering.
  This is possible with clEnqueueWaitForEvents / cudaStreamWaitEvent, by waiting for a *task*.
  The task you are waiting for must already have been dispatched to the GPU. In other words,
  you can pre-emptively launch a GPU task once it is dependent only on other GPU tasks
  (including H2D/D2H copying), and no purely CPU tasks (i.e. all of those must have finished).
  The best bet for implementation is probably the rewriting of multiple CUDA/OpenCL transformers
  into one.
- Re-implement all high level classes as Silk classes with methods in their schema.
- Serialize the topology of low-level contexts, including checksums.
  May help with faster caching of low-level macros.

*****************************************************************************

Call graph serialization
=========================
Seamless has fundamentally the following sources of authority:
- Dependence: cells dependent on upstream transformers, reactor outputpins,
  or low-level macros.
- Low-level authority: reactor editpins, the mount system, and the low-level library system
- High-level authority. This comes from 1) values in the call graph, or 2)
  the high-level library system (either via simple copying, or via a constructor).
  2) can be seen as a form of (high-level) dependence, but this is OK.

Cells that have full dependence are non-authority cells (they hold no
  authoritative state). Other cells are authority cells.
Structured cells can be mixed-authority, having inchannels that define some
 state but not all of it.

DOGMA: Authority may never pass from dependence to the high level. This means that:
- a high-level constructor must never react to a low-level cell change
- a low-level worker must never modify the call graph of its own context
  (but it may modify other call graphs)
- The topology of a high-level library must not be changed from the low level
 representation of that same library (but it may modify other libraries).

In PySeamless, the high-level API is a bit of a hybrid between high-level authority
 and low-level authority.
For *topology manipulations*, the API is a wrapper around call graph manipulator
classes, as it should be. However, *state manipulations* are typically passed
through to the low level, for efficiency.
However, the high level relies too much on this pass-through:
Silk operations (validation, schema inference) do not exist at the high level,
and neither does basic parsing of values (e.g verifying that it is really JSON,
if it goes into a JSON cell). This is fine if the low-level already exists,
 i.e. if there has been a translation.
Right now, *if there has been no translation yet*, the pass-through is delayed,
 and the state is stored in an ugly TEMP attribute of the call graph.
What needs to happen: the TEMP attribute has to go. Whenever state is modified
 before translation (of that particular piece of state),
 the particular piece of state must be translated in isolation; then the
 state manipulation is effected, and then the result is stored in the call graph.
The translated state must respect low-level authority (mounts, libraries).

Since dependence may never influence the high level, some rules must be
enforced.

- For mixed-authority cells, any authoritative state manipulation must
 have the same result regardless of what is in the non-authoritative part.
  Seamless will not enforce this, but normally it should be OK.
- Schema cells (or storage or form cells) may never have any dependence.
  If you want to generate them dynamically, use a high-level macro.

What stays is that after translation, the *low-level holds the authoritative
state of the call graph* (this is PySeamless's sovereignty idea).
This means that authoritative low-level updates (from mounts or reactors;
libraries are already linked to the high level) do not need to update the call
 graph. Right before re-translation or serialization, the call graph is filled
 with the low-level state (midlevel/copying.py).  


Modules, compiled workers, and interpreted workers
==================================================
UPDATE: At the high-level, non-main modules will be implemented as special Module
 and BinaryModule constructs. They will be linked to Transformers/Reactors/Macros.
 The main module of a compiled Transformer is something else
 (will have been implemented already earlier)
In principle, seamless allows a worker to be written in any language. (1)
Seamless will restrict the allowed values of a worker's "language" to a
list of recognized languages (mime types), but this list should be very long.
For every recognized language, seamless will classify them as:
- By default, "compiled" or "interpreted" (2)
- A default compiler (this can be defined even for interpreted languages, e.g. Nuitka or embedded-CFFI for Python)
Languages can then be subdivided as follows:

0) The Python and IPython languages are native to pyseamless.
Workers and modules can always be written in those languages.
1) For a worker written in an interpreted language, that language MUST be marshalled.
This would normally involve some kind of bidirectional JSON bridge. Some IPython magics implement marshalling as well.
Memory is never shared, always copied.
The interpreter is responsible for its own memory management.
2) For a worker written in a compiled languages, that language MAY be marshalled.
This essentially means: filling up a data structure (generated from the input and result schemas)
that can be passed on to the compiled language.
In addition, a header must be generated of the worker function.
(transform, code_start, code_update or code_stop) in the compiled language.
There may be different marshallers for the same language, e.g. a Fortran header may use the underscore name (gcc)
 or a full ISO C binding.
If no marshaller can be found, a C header is generated instead; the user is then informed that the worker function
 signature must match this C signature. Marshalling is then done using the default CFFI marshaller, which uses the
 C header.
 Cell memory management is always done by Seamless. The compiled function may allocate things internally, but these allocations
  may never become part of Seamless cells. The compiled function must have released all resources after transform()/code_stop()
  have finished.
3) Compiled languages in an extension module MUST be interfaced if their objects are PUBLIC.
*Interfacing* means: to allow the symbols of the public objects to be imported in the language of the worker.
Different interfacers can analyze the public objects of extension modules and tell if they are compatible
The following global interfacers (to Python) are defined:
- CFFI. Requires C headers for every public source object. Accepts C and C++ as public source objects.
  Requires fixed binary form for all arguments.
  Pure-plain JSON objects/arrays can become string, but mixed-plain for any argument is not allowed
- Numpy distutils. Accepts C, C++ and Fortran (using f2py) as public source objects. (see WIP)
- Cython distutils. Accepts C, C++ and Cython as public source objects.
- Manual interfacer (also for non-Python. Requires headers for workers written in compiled languages).
  Compiles public source object with -fPIC. The module becomes a shared library.
  Python must use ctypes to load it, or ABI-mode CFFI (manual header).
Private objects in an extension module are simply compiled to binary code objects and linked into the module binary.

Modules are always either compiled, or interpreted. If it is a mixture, there are
 four options:
 a  split the module in two modules. The interpreted module may import the compiled one.
 b  annotate the compiled source objects as "data". The interpreted source objects may
    then compile them on the fly (JIT)
 c  designate for each compiled source object (or group of source objects) one of
     the interpreted source objects as its "compiler". The module as a whole will
     be interpreted, with the "compiler" parts removed, but the compiled objects included.
     Example: CFFI build script.
d   have the compiled module marshalled to the interpreted language. Example. Cython-to-IPython using IPython magic.

Interpreted modules must have all objects of the same language, unless a transpiler is available.
IPython-to-Python transpilation is implicit.

A worker can be explicitly interpreted or compiled. The default is determined from the worker's language.
Workers may have one or two module pins, containing JSON of the module definition.
A compiled-language worker has a special optional module pin "main_module", containing *one* module definition,
 the main module dict.
It also has the option "marshaller" (default: the language-specific marshaller)
 and it has the option "interfacer" (default: auto-detect).
 If the worker is interpreted-language, an interfacer must be found.

All workers also have a special optional module pin "modules", which contains a *dict* of module definitions
The code pins are implicitly part of the main module. However, explicit "objects" entries for the code pins are possible.
"\_" is an alias for "code".
A module is a dict with at least an item "objects".
An "objects" entry for a source object may contain:
- The language (but not for a code pin), required. Seamless must know the language (in particular, its file extension)
- The source (but not for a code pin), required
- "compiled" or "interpreted" or "data" or "internal_compiled" (option c above, must contain name of other object)
- One or more private headers (in one or more languages) for sharing symbols with other objects.
  Format: (filename, value) dict. Filename includes file extension. Seamless will check that the filename won't clash
  with other headers or object-source-files-written-on-disk.
  No need to specify language. May be referenced (included) by own code (in own language)
   or by other object in the module (in that object's language), Seamless won't care.   
- Public or private (but not for a code pin), default: public (implies "compiled")
- Public C headers, as a language:header-code dict.
  Only for extension modules for interpreted workers.
  Needed if CFFI interfacer is used.
- Dependencies. Just for incremental (re-)compilation
  "../blah/X" will always refer to X in extension module blah (also inside the code, e.g. #include)
- List of exported symbols (if compiled, implies "public"). Necessary for IPython or .ipynb
- The compiler (optional, implies "compiled")
- "target": compilation mode (release, debug, profile; default is "profile")
- Compilation options: a list, a string or a per-compiler dict thereof
  (optional; if not defined, use default options based on target)
- The transpiler and transpiler options (optional)
- "marshaller": two scenarios where this is specified:
  1 In the code pin of the main module: a customized marshaller.
    For Fortran, seamless known the gcc marshaller (apply underscore), and the iso bind marshaller.
    They generate different signatures, and have different schema support.
  2 In an extension module, this is option d above. e.g. specification of an IPython magic

The module also contains:
- mode: "interpreted" or "compiled"
- language (only if interpreted)
The module may also contain:
- A compiler config dict, where locations of each compiler can be entered (else Unix "which" is used)
- A transpiler config dict, that also lists the target language
- interfacer
- Linking options
- Global settings: verbose compilation, debug compilation, build directory

In summary:
For pyseamless, interpreted workers in Python need no marshalling (3).
All other interpreted workers must be marshalled to and from Python (4).
Compiled workers may have their own marshaller, but that is mostly about generating
 from the schema the "signature" (telling the user the mandatory worker function declaration).
 Internally, the C header generated from the schema is used by CFFI, and this is the fallback.
For interpreted workers, extension modules may be defined.
Extension modules with all objects written in Python will be usable directly (3).
TODO: in .core, support for modules-defined-as-dicts-of-Python-cells, not just single Python/IPython cells
TODO: in .core, support for .ipynb cells (check language_info!)                

Compiled workers have a main module, of which the code pin source objects are implicit members.
 You may add additional extension modules, but this is tricky.

The whole point of a compiled module is to generate a shared module (for marshalling or interfacing).
In the future, this could be generalized:
- submodules, which generate statically-linked libraries (different bag of linked .o, plus public header )
- binary as end point, to be used with slash-language transformers (= interfacing via file system shell)
- implement caching + incremental compiling ("make" replacement).
  Already, internally, modules should be compiled to low-level BinaryModule, consisting of .o bag.
  This will be passed on to transformer for marshalling (CFFI) or interfacing (link into .so with distutils).
  In both case, use extra_objects (in set_source for CFFI, Extension class constructor params for distutils)
  The translation of module-JSON-to-.o-bag should become a low-level macro with a cell for each file
   (probably implemented using slash).

You can choose between marshalling and interfacing.
In general, marshalling is better, as you can share all Seamless schema's, and you have
 type safety. Interfacing only works for interpreted workers, it may require type declarations.

(1) But for the time being, macros will be written in Python, using the pyseamless.core API.
Therefore, "workers" will refer to reactors and transformers
(2) Or "kernel". Kernel languages have the restriction of both interpreted and compiled languages.
 They need a compiler, but they cannot be part of a polyglot module.
 The only pure "kernel" language would be OpenCL (marshalled using PyOpenCL).
 CUDA by default is in "kernel" mode (using PyCUDA marshalling), but it could also be
 in "compiled" mode (using nvcc, and then marshalled using CFFI as usual).
 OpenGL/GLSL is a bit of a special case. It definitely requires marshalling,
 but not in the context of polyglot transformers/reactors.
 Rather use the 0.1 library for marshalling (rip Spyder, parse Silk schemas).
(3) Including IPython, and including .ipynb (TODO)
(4) but if you can find a worker service that will accept the interpreted worker,
 it will do the job for you, problem solved.

The New Way of execution management
===================================
The New Way is purely a manager issue. Worker implementations are unaffected.
(however, now there is a sleep hack in kernel/transformer.py to prevent premature equilibrium; this needs to be removed)
- There will be only a single manager for every top-level context
- All checksums will be git-style but with SHA-256
- Only authoritative cells, object cells (cell()) and Python code cells will hold their value.
  For any other cell, only the checksum will be stored
  The value will be retrieved from a local cache dict
  The local cache dict takes checksums as keys.  
- Caching will be tricky for StructuredCells; the solution is
   a special Monitor backed up by caching.
   The authoritative part of the StructuredCell is always stored.
   Each outchannel and inchannel has its own relationship with the local cache dict, just as a cell does.
   Outchannels have a fallback mechanism where they ask their value of the authoritative part
   and/or the inchannels they depend on, as if they were the output of a transformer.  
   Even while being accessed, values could be removed from the local cache dict at will,
    and Python will eventually garbage-collect the accessed value.
    But a cache miss must trigger re-computation!
- Setting a value to anything non-authoritative will now be an error in Seamless.
  (This is anyway pretty difficult, as a high-level assignment would just modify the graph)
- Cells are (initially) considered "pending" if their checksum is known, else "undefined".
  Then, authoritative cells are marked as "equilibrium", as well as any outchannels/cells they
  are connected to.
  The manager considers workers as "undefined" as long as their inputs
  (and required editpins) are not in equilibrium. When they are known, a reactor
  is then considered "pending". A transformer (or a reactor marked as "pure")
  that is "pending" immediately becomes "equilibrium" under the following conditions:
  The checksum of the output cell is known, AND,
  the output cell is marked as "equilibrium" OR the grand checksum of the
  transformer is found in a computation server (see "services").
  A "pending" worker will have all of its inputs queried for their values, and
  then sent to them, becoming "running". The values will be queried using the local cache dict.
  In case of cache misses, checksum value servers can be queried (same as services do).
  If the cache miss persists, the cell's itself becomes "pending": its upstream dependencies
  (by definition, it has some) are changed from "equilibrium" to "running".
  A "running" worker will send values as normal. Once it is done, it may or may not be shut down.
  If it is shut down, its kernel is killed, and the worker is set to "equilibrium". Else, it is set
  to "equilibrium+"
  However, if the worker gives an error, the worker state is changed to "error" (or "error+").
  Upon entering "error", the worker does the following:
  All downstream cells are set to "error". A cell in error has its checksum invalidated, and propagates
   the "error" state to downstream dependencies. A running worker may or may not be shut down upon receiving
  an error, but at least, its computation will be interrupted. Its status becomes "error" (if shut down) or
  "error+" if not shut down. Workers may still be shut down after some time has elapsed.
  A reactor that shuts down for any reason has its "code_stop" evaluated (see "reactor side effects" below).
- The local cache dict can be configured to forget cache values. A separate dict records the time and
 the cell path. It may decide to forget when the cell path is destroyed or time lapses, or may maintain
 just one value per cell path. Each local cache dict is tied to a toplevel context.
- equilibrate() means that there are no "pending" cells and no "pending" or "running" workers. All cells
  and workers are either "equilibrium", "undefined", or "error". (Workers lacking input connections are
  "unconnected", which is a form of "undefined").
- equilibrate() can be invoked on individual cells, workers and contexts.
  As a flag, a blocking value request can be included.
- When an authoritative cell is updated (via reactor or from the outside),
  the cell is *first* re-defined as "pending".
  An "equilibrium" worker connected to an input that is now "pending", becomes "undefined".
  Same for a "running" worker, and it has also its computation interrupted.
  Only *then* the new checksum is set and propagated, potentially triggering workers.
- Reactors may also define *outputs* even after their code_update execution has returned
  (although it should be rare); this is treated the same way.
- There are "secret cells" for which a checksum may be set from the shell. However, they must either
  be connected to a service, or the checksum must give a cache hit.

An important advantage of the New Way is that there are stronger timing guarantees.
Example: dependency graph A=>B, A=>C, B+C=>D. If A is updated to A*,
B will become updated to B* and C to C*.
Eventually, D will be evaluated from B*+C*, but before, the intermediate computations
B*+C or B+C* are both possible as "glitches". But now the glitches disappear.

Test on Collatz test, this is a good measurement for equilibrate/unstable.

- Temporary
return_preliminary marks a result as temporary. Temporary results never trigger
 equilibrium.
Macros always ignore temporary results. Reactors and workers can be configured
 to accept them or not.


Auxiliary, ephemeral and execution cells
========================================
Execution cells are cells that contain only execution details and do not influence the result.
  Examples: number of CPUs, temp directory where to execute slash in, caching locations
Ephemeral cells are the same, but they indicate some hidden dependency.
  Examples: session ID, temporary file name, file with pointers in it (ATTRACT grid header)
  A reactor may have an editpin to an ephemeral cell, used for caching.
  Workers with an ephemeral output pin are never pure. But it is assumed that as long as the
   worker is not shut down, the ephemeral output is accurate.
Ephemeral cells are not authoritative and never eager. Usually, they are not stored.
Changes in execution cells or ephemeral cells do not trigger re-computation, but the worker
 will receive the new value once something else triggers re-computation.
 Auxiliary cells/workers/contexts are high-level only. Auxiliary cells and workers (as are ephemeral cells and
  execution cells) are stripped from a high-level graph before its grand computational checksum
  is computed. Examples: editors, loggers, visualizers.


Reactor start and stop side effects
==================================
The reactor start and stop code may produce side effects. To work properly,
 Seamless requires idempotency. For example, of the event chains below, not only
 must A and B give the same results, but also B and C. In other words, stop followed
 by start must cancel out in terms of side effects. Seamless has the choice of a
 spectrum between 1. never do a stop until the reactor terminates
 (and with the way cache hits work for the reactor, this may be at the end of the program),
  or 2. stop after every update execution, and restart whenever a new value arrives.
  1. may save CPU time, while 2. may save memory.
Some evaluation policy will tell Seamless what to do (this will not affect the result).
By default it is 1., which is essential in the case of a GUI in a reactor. (While the
  disappearance of the GUI technically has no result on the computation, it will definitely
  be an unpleasant surprise to the user).

event chain A:
set value X to 10
set value Y to 20
start
update
stop

event chain B
set value X to 1
set value Y to 2
start
update
set value X to 10
update
set value Y to 20
update
stop

event chain C
set value X to 1
set value Y to 2
start
update
stop
set value X to 10
set value Y to 20
start
update
stop

Thoughts on Seamless and purity
===============================
Seamless workers must be "kind-of-pure" in terms of cells: given the same input cell values, they must always produce the same
final output cell values.
This precludes the use of random generators, system time, or even the opening of an external file or URL.
Special input cells, Evaluation cells, do no count as input cell values.
This loose formulation of purity gives the following liberties:
 - Workers are allowed to produce different non-final (preliminary) cell values
 - They are allowed to have arbitrary side effects, as long as one of the following is true:
   - A) These side effects do not concern output cells
   - B) Or: they are idempotent in terms of input cells.
   For example, a transformer may open a GUI showing a progress bar (although a preliminary cell would be cleaner)
   Or, a reactor may compute the checksum of its inputs, store this in a database, and later retrieve the checksum and use it
    to produce the output.
 - They are allowed to send arbitrary values to special cells called Report cells (that reflect the status) and Logging cells
   (that accumulate values).
 - C) They are allowed to change cells via edit pins. This is considered an "act of authority", as if the programmer himself had
    changed this cell.
There is also a stricter formulation of purity: namely that B) and C) do not happen. Workers and contexts may be marked "pure"
 accordingly. In that case, they function as a single caching unit.
Non-pure (i.e. only "kind-of-pure") transformers are not normally shut down. It is assumed that when they shut down, they must be
 re-executed (which may be expensive). Reactors have explicit start-up and shutdown code, so they can be shut down at will.

Blocks
======
In Seamless, workers are expected to send values, for which they allocate the memory themselves.
Blocks are a (low-level) mechanism to pass around pre-allocated buffers of fixed size.
This mechanism can save memory, but more importantly, it is much more compatible with GPU computing.
Memory is not copied back-and-forth by every worker. Instead, buffers reside permanently on the GPU.

A BlockManager manages the block. It must be constructed with a namespace.
Namespace can be "cpu", "opencl", "opengl" or "cuda". Maybe in the future, new namespaces can be registered.
A block description consist of dtype, shape, stride, and offset.
A block description can be passed in to the BlockManager constructor,
 in which case the BlockManager will allocate the memory by itself. Alternatively, a pre-allocated Python object
 (Numpy array, PyCUDA array, etc.) can be provided via a set_block() method. You can call set_block() multiple times,
 this will invalidate all workers connected to the BlockManager (both input and output).
The BlockManager exposes a block inchannel and a block outchannel. Workers can declare their own block outputpins to
 write to the block inchannel. Once a worker has written there, the BlockManager will fire on the outchannel.
 Workers can declare their own block inputpins to receive Block outchannels.
 When the BlockManager allocates its block, each Block inchannel and outchannel sends two messages.
 The first message contains the pointer, the namespace, and the block descriptor of the block as a whole.
  The second message contains the specific block descriptor for the pin. Workers must verify that descriptors
  for input blocks and output blocks do not overlap in memory (see numpy.shares_memory and Diophantine equations),
  which is illegal.
 Whenever a worker has set a block outputpin (i.e. when it is done modifying it), it sends a message containing the checksum of
  the block content. Likewise, it receives such a checksum on its inputpin.
 Whenever a BlockManager receives checksum updates on its inchannel(s), it computes and stores checksum updates over
  its outchannel(s).
 A BlockManager may define one *tiling shape* and many *tiling channels*.
 A tiling shape is like an array shape ("length" for each dimension). Length must be a divisor of the
  number of elements for that dimension (this is verified as soon as the block descriptor is known).
  The block is tiled over "length" tiles in that dimension, and the memory is divided equally over each block.
   For every tile, a block inchannel and outchannel can be defined.
   A tiling channel can be inchannel or outchannel, they work exactly like StructuredCell channels, but instead of
   property paths, they contain index paths (although if referencing a struct array, the last few elements
   of the index paths may be properties). Only single indices: ranges and steps are not supported.
   This is a way to process parts of the buffer independently.
   As for StructuredCells, it is checked that the inchannels and outchannels do not overlap. [HUH? they *should* overlap! an outchannel should fire whenever one of its inchannels is modified AND all constituent inchannels have submitted a value]   
  The top-level block outchannel only fires when all tiles have been received. [*all* outchannels do so]
 Block inchannels can be invalidated, which is propagated to the outchannels.
 It is possible call a method swap_buffers: tile[1] points now to tile[0] and vice versa. Each connected inchannel
 and outchannel will get an invalidation signal and then receive the new block descriptor.
 [hmm... maybe not; let the users build the 8-shape topology themselves]
Namespaces are part of the block pin declaration. Seamless pin protocol takes care of namespace mismatches, e.g.
 copying data between CPU and GPU (this is blocking, so not the most efficient).

Caching of blocks works similar to caching of structured_cell, namely at the level of individual inchannels and outchannels.
BlockManager-BlockManager is not possible, but block *pins* get processed as normal. The very first message has its pointer
 translated, all other messages are forwarded, with the contents serialized and put into the other buffer.
 Again, the Seamless pin protocol takes care of namespaces.

Streams
=======
Streams are sequences of messages. The number of messages is not always a priori known, and may arrive in any order.
A standard message has a key, a celltype, a checksum and (optionally) a value.
The checksum/value corresponds to a "buffer" representation of a standard cell, or a "state" representation for a structured_cell.
A transformer may declare stream inputpins or a stream outputpin.  
A stream may send standard messages, the "invalidate" message, the "no more keys" message, or the "close" message.
It may receive a "value request" message, consisting of a key (and celltype+checksum, just to check), a "discard" message
(meaning that no more value request will come for that particular key),  and the "finished" message
(meaning that no more value requests will come for any key).
Value requests are non-blocking, it simply means that a message with value will come.
(In case of multiple consumers of the stream, Seamless will buffer the value message until discard messages have been received
  from all other consumers)
The transformer is expected to read all messages from stream inputpins before exiting. It may send back value requests,
it should send back a "discard" message for the other keys, and finally, it must send a "finished" message back.
(if not, it is considered as an error). If multiple transformers connect to the same inputstream, discard messages and finished
messages are withheld by seamless until all transformers have sent the same message.
A transformer with an output stream is expected to send standard messages followed by a "no more keys" message.
In addition, it must poll the output for value requests, until a "finished" message has been received.
Then, it should respond with a "close" message.
Value request can be polled before or after the "no more keys" message, but exiting before is considered an error
(and will invalidate the entire stream).
The transformer should respond to value requests by sending the value for the requested key in a standard message, but not
 doing this is not an error. However, the value-requesting transformer should raise an error if it gets a "closed" message
 before its value request was honored.
"Do-it-yourself" streams can be programmed in Python by inheriting from StreamInchannel or StreamOutchannel.
In addition to observers, this is the only way to interact with Seamless in a reactive (rather than imperative) manner.
You will need to provide some kind of callback or backend to process requests.
NOTE: streams are fundamentally uncachable.
A transformer or context with stream inputs can only be sent to an interactive service.
A transformer with stream pins will always be re-executed after macro execution.
For this reason, low-level macros that generate stream transformers are generally a bad idea.
However, stream transformers (and low-level macros that generate them) can be part of a pure context that does not have
 any stream inputs or outputs. (At the high-level, streams that are part of non-pure contexts flag a big warning).
 Such a pure context gets cached independently (without translation, even), and this will elide the stream execution.

Special constructs
==================
These are special constructs with generic application, as they use serialized high-level graphs.
The graph must be pure and have one or more exported outputs.
Each special construct has a reference implementation. The checksums of the
 reference implementation code are always considered as ground truth.
They can be executed as every other Seamless service in this way.
However, services may accept reference-implementation special construct requests,
but process them with a very different optimized implementation under the hood.
All special constructs are implemented as transformers.

- Apply
(non-interactive)
Takes a serialized graph, a mixed-cell dict of input values with keys corresponding to the
 input cells/pins (i.e. a grand computation).
The computation is checked for cache hits. Both the checksum and the value must be found.
The graph is translated, the input values are connected, the context is equilibrated,
 the result values are returned.
 Store the result value in local cache.
(interactive)
The inputs can be changed. (syntactically, works much more like a normal transformer, except
  that there is the additional graph pin).
UPDATE: The text below will be true for all of seamless!
(Cache hits are being explored as soon as the checksums are known; values can be lazy.
By default, only the result checksum is returned.
The service accepts value requests for the output.
Serve all value requests from local cache; cache misses lead to recomputation.)


- Map
(Interactive)
Takes in an input stream, a graph and an output stream. Applies the graph to every item in the stream.
Needs a description to which input cell to bind the input stream, and from which cell to read the output.
Does not support multiple streams, but you can do the zipping and unzipping yourself.
Reference implementation:
Import seamless and embeds the graph in an (interactive) Apply graph.
Iterate over all input keys. Call the Apply graph and let equilibrate. Forward all returned key+checksums.
Reverse-forward all value requests to the Apply graph.
Forward all invalidate messages (interrupting embedded graph). Forward no more keys messages and close messages after computation.
Forward all finish and discard messages from output to input.
(Non-interactive)
Embedded Apply graph is non-interactive.

- Filter
Like Map, but this time the graph must return a boolean (keep it or not).
(Interactive):
  send back discard messages if false. Forward the message otherwise. Reverse-forward
  all downstream value requests.

- Split
Like filter, but produces two streams (the True stream and the False stream)

- Reduce
Takes in an input stream and a graph, and a result.
Requires an initial value, and a secondary input cell in the graph (for accumulation).
Use an interactive Apply graph to accumulate. Tell the graph not to cache the graph-as-a-whole,
 as keys are unordered.
Iterate over the keys. Immediately ask the value of every key.
For the first key, write the initial value in that cell before executing.
For all subsequent keys, write the result for the last key.
Once all keys have been processed, return the result.
(Non-interactive)
Embedded Apply graph is non-interactive.
NOTE: for floating points values, reduce can easily lead to non-determinism,
 since streams are non-ordered and flops are non-commutative (see Order special op below)

- CyclicIterator
Performs a fixed number of iterations of a cyclic graph.
There must be the fixed number of iterations N.
There must be an iteration variable: a variable that has an initial value, and
 where the result of the computation becomes the input for the next computation.
There may be multiple such iteration variables (although there is only one loop).
Each variable can be indicated as "accumulate" or "last". "last" keeps only the last value.
"accumulate" accumulates into an array or a Block.
Reference implementation:
- Allocate an array for every accumulated itervar
- Allocate input cells for input
- Allocate output cells for every itervar
- Translate the graph, connect it to input and output cells (using non-interactive Apply)
- Assign the (initial) input values to the input cells, and equilibrate.
- For N iterations: read the itervars from the output cells. Accumulate if needed.
- If not the last iteration: write the itervars to their input cells, and equilibrate.
- Return the itervars (accumulated or not)
It is possible that an itervar is an array or a Block.
In that case, the input and output are a two-tile block,
 and swap_buffers is invoked after every iteration.
CyclicIterator is always non-interactive.


Utility functions
=================
Sort: stream1 => stream2. sorts the keys of stream1 and creates a stream2
 where the keys are the sorted indices.
Order: stream1 => stream2, where stream1 has numeric keys.
  stream2 is equal to stream1, but its behavior is now ordered:
  key N+1 will only be returned after key N has been requested and returned.
Zip: zips N streams into one, like Python zip.
Convert from mixed/json to stream. Keys can be the first-level
 keys of the dict, but also second-level or deeper, or up-to-second-level.
Convert from stream to mixed/json. Keys must either be strings, or the same
 level encoding as above, or integers (this will produce a mixed/json array)
 (In addition, array chunking must be possible as well)
Convert between Block and stream; requires integer keys of the stream.
Convert between Block and mixed/json; mixed/json must be organized as an array.
NOTE: if the stream messages are big enough,
 the mixed/json cell that is converted from/to stream can be much more
 space-efficiently value-cached by storing the value as a set-of-checksums-of-messages,
 rather than the value as a whole.
 This is because each message will already be value-cached at some point.

Cyclic graphs
=============
Strategies to model them:
1. Don't model cycles with seamless (keep cycles inside a single worker)
2. Explicit cells for every assignment (if number of iterations is known).
   First assignment to cell x becomes cell x1, second assignment to cell becomes x2, etc.
   Would be feasible on very long term, with cells being very low-footprint
    and caches eager to be cleared. Otherwise very space-intensive.
3. Use an CyclicIterator (see Special Constructs). if number of iterations is known.
   Build a high-level graph g that performs the computation, and send it as data   
4. Nested asynchronous macros (but seamless will warn of cache misses, and
   space requirements can be atrocious)
   Example: collatz.py in low-level tests
   but Seamless cannot currently deal with this beyond 10-16 iterations or so,
     even though this example is in fact synchronous
Solutions can be combined, of course.

Registering commands with domain-specific languages
===================================================
Some domain-specific languages, such as slash-0 and topview, rely on a vocabulary
of registered commands. This is done as follows:
- A macro to interpret the source code of the DSL, generating a context Z
- A dictionary with command name and their parameter declaration. This dict
  will be an extra input parameter of the macro.
- A dictionary with commands, containing the command name, a unique command ID,
  and a mapping of each parameter to the name of a pin/cell/channel in Z.
  This dict is generated as an additional "magic-name" cell in Z by the macro.
- Instantiation code for each command. Essentially, macro code which can constructors
  a live instance (context or worker) that can execute the command. This will almost
  always be a macro that must be bound to a lib.
- An instantiator. It receives both dictionaries, and the instantiation code for
  each command.
- A dynamic connection layer that receives:
  - The second dictionary
  - The context Z
  - The command execution context generated by the instantiator.
  It will read the "magic name" cell from Z, and use its contents to build
  connections between Z and the command execution context.
- If the macro that generates Z can be also the instantiator, then the dynamic
  connection layer will be superfluous.

Idris evaluation
================
Very long-term. From a grand computation description D, one can generate Idris
 parsers in the same way as Idris type-safe printf.
One such parser converts D => Idris input type, Idris output type
Another converts Idris input data + D => Seamless input JSON J1
A Seamless launcher is a function that converts J1 to Seamless output JSON J2
  by launching remote (non-interactive) Seamless server
Another parser converts J2 + D to Idris output data.
This allows (non-interactive) Seamless services to be linked in a type-safe manner, amenable to proofs,
  and using the entire toolkit of functional programming (map, reduce, etc.)
Lazy output cq. lazy input cells in Seamless services can be exposed as callbacks-into-Python
 (CFFI supports this) cq. callbacks-into-Idris-functions
 (Haskell FFI at least supports this; Idris FFI does not support closures, that's bad).

 NOTE: seamless will never have any global undo system. It is up to individual editor-reactors to implement their own systems.

Plugin-socket connection system
===============================
Seamless will have a hive-like plugin-socket connection system to connect reactors.
These reactor connections are *not* meant to influence computations, but only to improve visualization
 and authority control.
Use cases:
- Have reactor 1 that polls a database, and reactor 2 that has an editpin to modify cell X.
  When reactor 1 and 2 are connected, cell X can be modified (as an act of authority) when the database
  is modified.
  Conversely, if reactor 2 receives updates to X, reactor 1 could store them in the database. For this,
  X could also come from an inputpin.
- Reactor 1 maintains an OpenGL window, and reactor 2 draws in it. When connected, reactor 1 can notify
  reactor 2 when the drawing can take place (since in OpenGL, drawing must take place within a specific 
  callback triggered by the windowing system; With Vulkan, this may no longer be necessary).
- Reactor 1 and 2 both maintain a GUI using a native widget. By exposing their widget objects to reactor 3,
  reactor 3 can display them in a common window.

NOTE: TO DOCUMENT:
Seamless should make it easy to write code that runs fast (e.g. in parallel, in C, on the GPU) with
minimal effort. However, Seamless does *not* by default have a high performance in terms of 
data handling: a lot of things are copied and have their checksums computed, repeatedly.
Seamless should provide the facilities to make data handling faster, usually at the expense of error 
control, but users will have to enable them if they see that their data load gets too heavy.
TO DOCUMENT (= example of the above):
Structured cells are pretty efficient when it comes to state-modification-to-outchannel mapping. 
When you set .a.b, it will fire on outchannels .a.b.c, .a and self, but not on .a.d, a.d.e or .f .
For other outchannels, not even the checksums will be computed (TODO: not true at present)
This holds no matter if .a.b is set from an inchannel or from the terminal.
However, this efficiency is *lost* when you use any kind of buffering or forking. This will set the entire
 state, causing all checksums to be recomputed.
In addition, it is pretty *inefficient* if you make repeated state modifications; for example,
"for i in range(100): cell.a.b.append(i)". Outchannels connected to a transformer will repeatedly cancel
 the transformer, and those to a reactor will *wait* on each append until the reactor has finished!
Therefore, any Silk method that modifies the data should normally use fork().
(to think about:
- storing some selected bytes of a big array, to quickly detect huge changes w/o recomputing full checksum
- Make a special StructuredCell Silk mode where set/setitem are not intercepted by the monitor, but where
  instead any outchannel update must be triggered manually by sending a dirty signal )