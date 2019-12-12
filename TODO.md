E. The mid/high level
- High-level links; maybe (re-)implement them at the low level 
  (double edit pin is not good)
  Must be between simple cells, that have no incoming connections; no support for transformer.code; later support it for .schema/.result_schema.
- Reactors
- High-level Macro construct around low-level macro; 
  shouldn't be too hard, but connections could be tricky.
  Wrapping everything in a single Macro with some connections into .share, .mount etc.
   is a good way to get sth working quickly, until the high level works well.
3. Run tests
3a. Test in Docker container
4. Test in Jupyter
5. Test Observable Notebook (client JS has changed)
6. Re-run examples, in particular capri and snakemake

Medium term:
- What happens with error messages of setting simple cell values?
Structured cells have .exception... so do (simple) transformers and macros. 
What about reactors? There are also the core aux systems
(mount, share, communion). Once we capture those error messages
(and link them to cells if possible), are we done for logging errors? (apart from translation errors of course)
- Allow structured cell schemas to come from upstream
(same as currently for transformer code). This requires
the disabling of type inference.
UPDATE: instead, schema can be high-level linked to a simple cell!

Long-term: buffer cache references are not reliable, especially with
hash patterns (without, they *seem* to be fine, but some fishy things
happen at the midlevel...)
The double decref warning has been disabled for now...
For production, don't rely on buffer cache, but have Redis as a backup!!


=======================================================  
SOMEWHAT OUTDATED: until: see below

Great Refactor is almost complete (see seamless-towards-02.md).
Things to do:

Seamless is now usable by me, to port RPBS services/Snakemake workflows to interactive and reproducible services
 Need some more months to make it usable:
- by other devs
- by sysadmins (job control, deployment)

1: Towards a first real example
- high level: reassigning transformers does weird stuff, and equilibrate seems necessary everywhere
- Get reactors working again at the high level
- Traitlets (move to low level?)
- Constructors, finish testing
  Test library-containing-another-library    
  Make sure constructors work correctly when copying parent contexts
  Test indirect library update system, also with constructors

- Finish browser lib
-  First real example:
  - Convert topology.json (of a different ctx!) to SVG
  - Interject merge for manual edit
  - Hook up browser for visualization

intermezzo: re-run all tests


2:


A. Deployment: Seamless Hub
  - Register graphs to spawn request
  - Spawn request: Open a random channel, instantiate graph
  - Redirect shareserver traffic (REST and wss) to instance.
    - Notions of internal (localhost) and external URL
  - Redirect communion traffic to instance 
  - Advanced: monitor instance state. When long unchanged: translate back to graph, and store. 

B. Usability
- Implement reactor
- Implement annotation dict, including debug (DONE), ncores (ncores DONE)
- Every worker has a number of cores used (default 1). As many jobs are launched as there are cores
- Shell (create new namespace upon request/upon update; either pre-execution or post-execution [post-execution may re-execute transformer/macro])

C. DaReUS-Loop/PepCyclizer example:
  - Banks!
  - Not command-line based, i.e. don't use SnakeMake, use BCSearch routines
  - Need high-level Macro structure: needs deep structure, and automatic transformer
    map/reduce has now been ripped.
  - PyPPP docker image: code is open source, but SVM model is secret

D. Documentation
- Update interoperability document
- Prepare simple demo notebook
- Prepare some docs (at least stubs)
- Update Github


Cleanup
   - Fix cancellation policy wrt structured cell (now, everything is cancelled,
    which prevents expression morphing (i.e. data value will always be fetched)
    and makes modified_auth_paths/modified_inchannels useless) 
   - Adapt graph format wrt structured cells. Do we need to store
     "buffer" *and* "value"? They are always the same!
     Better to make some kind of "validated" attribute
     Also, when loading the graph, if it is trusted, not only update
     transformer cache and expression cache with elements mined from
     the graph, but also prevent StructuredCell joins if validated=True
     => loading and equilibrating an equilibrated graph should do nothing, no transformations and no data loading!
   - Implement old lib.gui.edit as a new library, with new editpin.
   - Terminology: context children can be private, in which case they are not in __dir__.
     By default, they are public. No more "export".
     (In general, look at __dir__ in the context of Silk, mixed, and cells)
     (NOTE: This has nothing to do with services. Services determine private and public based on
     what connects into the serviced context.)
   - Start with lib porting. Port Qt editors (including HTML), but no more seamless.qt
     Port all macros, but store the code in plain Python modules in lib, that register a library context   
   - Jettison Plotly and OpenGL for now; re-target main focus of Seamless towards scientific computations for now
   - Cleanup tests. With direct mode, most low-level tests should work now? Other ones can be ported to high-level    
    - Tests involving OpenGL can be jettisoned for now
   - Cleanup of the code base, remove vestiges of 0.1 (except lib and tests).
   - Cleanup of the TODO and the documentation (put in limbo). Don't forget /docs/WIP!


/SOMEWHAT OUTDATED
2. 

=> Release 0.2

Build docker images

A. Workspace manager (+ web interface), proof of principle.
see data-management.txt
Follow up:
Needs some kind of provenance/Google-your-checksum server 
Clean up Redis keys that are old and have no workspace/minispace associated with it. 

B. Finishing touches (tests/TODO)

C. Supervisor.
Coordinate job submission on the cluster and provenance 

D. Logging and graph visualization, initial prototype
(see Status-of-seamless.txt)
NOTES:
- status mostly gets reconstituted (except reason for void)
- metainfo:
    - store exception and stdout/stderr of a transformation, include in status report
        also store if result was obtained from cache, or remotely
    - same for macro and reactor (easier, because 1:1)
    - same for cell:
        - structuredcell validation error
        - error in obtaining value from checksum (also if provenance fails)
    - implement storage for metainfo in graph
- logging system, based on event loop (in parallel to metainfo)
- progress bar system (connect to progress)

1. Rip GPU cell scheme, this will never work.
 Instead (long term plan):
 - Annotate transformers as GPU-based. This will make all of their pins GPU-based.
 - GPU-based transformers produce a GPU-based result. Checksum computation of this result is done on the GPU.
 - Maintain a checksum-to-GPUbuffer cache that maintains which buffers are on the GPU
   Can be done smarter for certain expressions (introduce offsets and stride)
   Cache can be emptied based on memory requirements, or if certain checksums are foreseen to be not needed
    anymore on the GPU.
2. Rip pure reactors. This will never be supported


End of the Great Refactor
Seamless is now kind-of ready to be started to be used by other devs, at their peril, caveat emptor, etc.
Limiting factor: lack of documentation/examples

Next step: the roadmap of Status-of-seamless.txt

Delay for later:
1. Dealing properly with explicit None values.
Make it so that transformations and reactors CAN set None on their result
(Allow any worker inputpin to be annotated as must_be_defined=False.)
 Same for None explicitly set on cells (cell.set_value(None), or cell.set_none() by a graph;
  cell.set_void() explicitly sets a cell to void-None)
 Read accessors that retrieve None when reading their path (as opposed to AttributeError/KeyError)
  also are considered "explicit None".
 Transformations that resulted in an exception are NOT explicit None (they are "void-None").
 Explicit None values are NOT void and do NOT lead to void cancellation
 Explicit None values are allowed on input pins that have their support explicitly enabled.



*****************************************************************
UPDATE, Feb 2019  (pertains to text below)
The New Way/Great Split prioritization has rendered moot much of the roadmap below.
It needs to be reorganized, and the following tasks to be added:
(and integrated in cloudless/"Towards flexible and cloud-compatible evaluation")

Notes:
1.
- Reactor execution.
  - Pure and semi-pure reactors can be executed async, just like transformers.
  - Because of this, they can be cached and submitted as remote jobs.
    Reactcache could be set up similar to transformcache.
    Better: generalize transformcache into async_cache to include pure reactors and graphs.  
- Remote interactive mode execution.
  Semi-pure reactors can be remotely executed in interactive mode. Deltas are sent,
  and responses are received. The state itself must be labeled with an increasing ID,
  just as for shareserver. (Semi-)pure graphs can be executed in the same way.
- Graph remote execution. Only for pure graphs, i.e. that contain no impure reactors.
  They can be executed non-interactively (as if a transformer) or interactively 
  (as if a semi-pure reactor).
- This is all orthogonal to collaborative mode, which deals with graphs but allows dynamic
  modification of the entire graph (whereas interactive mode is just the value of pins/cells).
2. 
- Non-deterministic outputpins. These are essentially editpins, except that
   the reactor is NOT notified if they are changed by some external source.
3.
- In the future:
  - Every cell will be associated with one or more seamless top context IDs (scids)
  - scids, cells, transformers can be annotated. Best front-end is probably to annotate
    an entire top-level graph and then submit it to annotation server.
  - Extend simple transformer caching with high-level graph caching
  - When scids get re-defined, it is possible to obsolete associated checksums
    (clearing value cache, define obsoletion server entries)
  - Use username/origin on transformer caching, user authority on scid/annotation
  - Lots of reverse servers
*****************************************************************

Part 4: Towards release

4A: Port the peptide trajectory editor, use Observable instead of Jupyter.
   Build upon struclib

4B: get BCsearch working
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

0.2 release
Documentation, make at least something sparse
Reorganize this TODO into Github issues
Make new videos:
  - Basic example
  - Something with C/C++
  - Something with web forms/interactive notebook (some elements of part 6)
  - Docking
Seamless is now becoming usable by other devs, but needs a lot of patience (correct Jupyter version etc.)
Lack of documentation still a big issue.

- High-level construct for macros (by definition low-level) with language (python) and api (seamless.core) fields.
- Call graph serialization. WILL HAVE BEEN DONE ALREADY.

- The New Way of execution management (see below).  WILL HAVE BEEN DONE ALREADY.
- Seamless mainloop and equilibrate should now integrate with asyncio/nest_asyncio. No more dirty things
  regarding work flushes. This should make Seamless compatible with modern (autumn 2018) versions of
  IPython, ipykernel and tornado.
  Don't forget to look into the stdout swallowing that currently happens (Wurlitzer?)  
- Re-introduce caching for non-pure low-level reactors
    They give a cache hit not just if the value of all cells are the same, but also:
         - if the connection topology stays the same, and
         - the value of all three code cells stays the same
    In that case, the regeneration of the reactor essentially becomes an update() event  


Intermezzo:
  - Fully port over 0.1 lib: from .py files to Seamless library context files
  - Fully port over 0.1 tests
  - Clean up all vestiges of 0.1 (put them in WIP if needed)
  - Update documentation
  - Seamless installer
  - Initial docker integration

0.3 release
Lots of videos and notebooks, also of a more ideological nature
Start promoting Seamless as something that starts to be useful for outsiders. Error messages are becoming limiting.

Part 5:
- Cell sharing must support unidirectional sharing (easy!)
- Some more services proof-of-principle   
  Low-level services (non-interactive transformer) will have been done
  Other possible services: interactive transformer, pure reactor (non-interactive or interactive)  
  NOTE: These are strictly core.manager concerns. Neither the workers nor
    the high-level has anything to do with it!
- "Simple mode" translation of transformers and reactors (no structured_cell, no schema)
- High-level: pure contexts. Pure contexts have at least some public output cells and output pins.
  Only pure contexts are can have a grand computation result: the checksums of the public outputs are what is being
   stored as the result of the grand computation.
  Connections to private output cells/pins are not forbidden, but lead to a loss of purity (with a big warning),
   as does demanding their value from Python.
  Reactors and transformers can also be marked as pure (the high-level makes transformers pure by default).
  In both cases, all output pins are public.
  If they maintain their purity, a pure object is an independent caching unit. A hit in the
  computation checksum server will avoid the pure object to be (re-)translated at all.
  Also for the purpose of low-level caching, pure objects are a single dependency unit (a "virtual transformer"),
   so the low-level must be informed.  
  UPDATE: everything is pure now

- Build upon services proof-of-principle (cloudless) MOSTLY DONE
- HMTL gen from schema
  non-interactive => relatively easy but unimportant; need to think about result display
  interactive (REST calls) => tricky
- Implement all the checksum servers DONE
- Improved docker integration: bundle with servers, cache server, cache volumes MOSTLY DONE

0.4 release
Documentation  
Make new videos:
  - Making web services
Seamless starts to be usable as a service deployment tool. Limiting factor becomes flow control.
Contributing is still hard because the code is still a mess.

Part 6:
  - Set virtual filenames for (non-compiled) transformers. See tests/highlevel/python-debugging.py
    Maybe integrate with gdbgui
  - Signals. UPDATE: make them a special case of plugin-socket (see below). Probably delay this until long-term

Intermezzo:
Do a bit of code cleanup
Have a look at all Python files. Move in-code TODOs etc. to documentation
Start to reorganize some code, rename some APIs, etc.
Perhaps a bit more formal unit tests
Have a look at what it would take to go to PEP8 compliance.


0.5 release
Seamless is now in alpha; all missing features and the most annoying bugs should now be in Github issues.
Start to solicit for help.

Part 7:
- High-level mounting is not quite satisfactory (redundant "translated" context)
- The high level should store all permanent state in the graph nodes,
    nothing in the class instances. This way, the user can add their own syntax
    to manipulate the graph. (highlevel.ctx.\_children should go as well).
- Start with report channels that catch error messages, cache hits/misses etc.
   Gradually make Seamless such that it never crashes, but reports everything
   Kernels should be killable from shell (deactivates manager too)
- "only_auth" option in mounting context, mounting only authority cells
   This should be on by default
- Silk: error messages, multi-lingual (use Python format() syntax, but with properties to fill in, i.e. "The value cannot be {a.x}". This is natively supported by Python. No magic in the style of {a.x+a.y}; define a property for that)

0.6 release

Part 8:
- Foreign-language integration
  - Extends the C/C++/Fortran proof-of-principle
  - Support CUDA/OpenCL
  - Requires also a Silk extension (GPU storage, fixed-binary, see silk.md)
  - IPython (.ipy)/Cython magic is not (or barely) necessary, since IPython is natively supported by workers.
- Bring back OpenGL support
- Port over Orca and other examples
- Make new videos:
    - Fireworks
    - 3D
    - Docking
    - Orca (don't show the code)  

0.7 release
Seamless is now in beta. Shift attention to API stability, unit tests, etc. Learn about best practices,
 and ask for help.

Medium-term:
- Re-enable remote module compilation jobs
- (UPDATE: DONE. Just get my patch into pandas...)
  Add Pandas as a query engine. Querying in Pandas is fantastic (much better than numexpr).
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
-  disallow low-level modification of cells under macro control.
- Meta-schema for schema editing (jsonschema has it)
- More love to the GUI around report channels (to visualize) and around high-level context (to edit)
  At this point, some proof-of-principle should exist already.
- Windows support? Or never? Or just with local jobs disabled?
- An extra "table" celltype, for text (like awk or org-mode) or binary (like Pandas)
- Support more foreign languages: Julia, R, JavaScript. IPython magics, also have a look at python-bond
- API to construct transformations without low-level contexts, launch them, and to check for cache hits.
  Application 1: to implement efficient non-deterministic execution that gives a deterministic result.
  Examples are: reduce or sort on deep cells that arrive piece-meal, or where the data may be near or far.
  Application 2: cyclic dependencies.
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
- Set up user library directory and robogit. User contributions to the stdlib should be made easy.
- Checksum cells (YAGNI?)
Contain a checksum in hex value.
Can be trivially converted to text, str. Can be re-interpreted from text, str.
All other conversions are based on re-interpretation (see below)
If connected from a non-deep cell, the value is equal to that cell's checksum attribute.
If connected from a deep cell, the value is equal to that cell's deep structure (as dict/list).
Likewise, when connecting from a checksum cell:
- A non-deep cell checks that the checksum is a single checksum, and accepts that as its own checksum
- A deep cell checks that the deep structure is correct, and accepts that deep structure as its own.
Since checksum cells can be bound to macro paths, and deep cells cannot, this is currently the only way
 to connect deep cells inside a macro to the outside.


Very long-term:
- Python debugging (see seamless-towards-02.md)
  UPDATE: native widgets are probably outdated, but some network channel (Jupyter protocol?)
  would probably be good. Keep an eye on analogous developments in VS Code and JupyterLab.
- Full feature implementation of Silk, e.g. constructs (see silk.md)
- Other *host* implementations? JavaScript? Erlang? Elixir? Go?
- Re-implement all high level classes as Silk classes with methods in their schema.
- Serialize the topology of low-level contexts, including checksums.
  May help with faster caching of low-level macros.

*****************************************************************************

Call graph serialization
=========================
UPDATE: never ever save values in a call graph, only checksums and statuses!
UPDATE: only ever load authoritative values from a call graph, load the rest into cache

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
state of the call graph*.
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
2) For a worker written in a compiled language, that language MAY be marshalled.
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
- Need asyncio, to move beyond tornado 4 / ipykernel 4
- There will be only a single manager for every top-level context
- All checksums will be git-style but with SHA3-256
- Only authoritative cells, object cells (cell()) and Python code cells will hold their value.
  For any other cell, only the checksum will be stored
  The value will be retrieved from a local cache dict
  The local cache dict takes checksums as keys.  
- Caching will be tricky for StructuredCells: UPDATE: see livegraph branch  
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


Execution cells
========================================
Execution cells are cells that contain only execution details and do not influence the result.
  Examples: number of CPUs, temp directory where to execute slash in, caching locations
Changes in execution cells do not trigger re-computation, but a reactor
 will receive the new value once something else triggers re-computation.


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
There is also a stricter formulation of purity: namely that B) and C) do not happen. Reactors and contexts may be marked "pure"
 accordingly. In that case, they function as a single caching unit.
Transformers must always be pure, no side effects allowed other than Report/Logging cells.
Impure reactors are not cachable and will always be executed (unless they are part of a pure context
 that gave a cache hit). Only impure reactors can take Report/Logging cells as inputpins. But you
  can always "cast" them to a normal cell (this normal cell will be authoritative).
Semi-pure reactors are not normally shut down, because of performance.


"Transform lazily, react eagerly"
=================================
Imagine the case where a graph has just been loaded. You know all checksums, but not the values.
For now, all values must be stored in an accompanying cache archive.
In the future, make it possible to store just the authoritative values.
When a non-authoritative cell value is requested, and there is a cache miss, 
 travel back the graph and evaluate the transformers to re-compute the result.
This should be enabled/disabled on a by-cell basis (if any cell upstream has it
 disabled, don't do it).

Cyclic graphs
=============
Strategies to model them:
1. Don't model cycles with seamless (keep cycles inside a single worker)
2. Explicit cells for every assignment (if number of iterations is known).
   First assignment to cell x becomes cell x1, second assignment to cell becomes x2, etc.
   Has become feasable now that cells are very low-footprint, but
   caches must be cleared or memory consumption is too high.
3. Nested macros (for recursion)
   Example: collatz.py in low-level tests. Works well now
4. Explicit transformation/cache API within a single worker.
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
- Instantiation code for each command. Essentially, macro code which can construct
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

Improved SnakeMake integration
==============================
Seamless has SnakeMake support by letting SnakeMake build its DAG, and then
 convert this DAG to a Seamless context.
This is currently done using the snakemake2seamless command line tool, also
 because high-level macros (contexts with constructors) are not yet working.

SnakeMake *always* pulls, having as target a rule output or a set of files. 
If it is a rule, it may not contain wildcards. Therefore, SnakeMake always has well-defined, statically known output files.
This is not always so for inputs and intermediate results. SnakeMake has two mechanisms
 to dynamically determine the input files of a rule. The "dynamic" flag delays the
 evaluation of a wildcard file pattern until runtime. It must be declared as the
 output of one rule, and, identically, as the input of one or more other rules.
 This mechanism is being deprecated in SnakeMake 6, in favor of checkpoint rules.
 Checkpoint rules are to be used together with input functions. If an input function
 tries to access a checkpoint rule, the input function is halted until the checkpoint
 rule has been evaluated, and then re-triggered. (Note that in all other cases, input functions are evaluated while the DAG is being built, so no special Seamless-side support for input functions is necessary.)
*Seamless will never, ever support either of these dynamic mechanisms*. 
If you need dynamic DAGs, you need to do the dynamic part in Seamless, letting it generate a (static-DAG) Snakefile if needed. 
Example: 
Snakefile 1 takes a static number of input files to create a single clustering file. Snakefile 1 can be simply wrapped in a Seamless macro that does the same as snakemake2seamless. It requires the target rule / file list, a Snakefile, and optionally an OUTPUTS (see below)
Snakefile 2 splits the clustering file into a clusterX.list for each cluster X.
It may be a single rule that generates all the outputs; in that case, it must depend on a list OUTPUTS, e.g. ["1", "2", "3"]. OUTPUTS must be generated dynamically by a custom Seamless transformer that reads the clustering file, counts the clusters.
Snakefile 2 can then be generated by a general-purpose transformer that takes in a
rump Snakefile and outputs list and adds 'OUTPUTS = ["1", "2", "3"]' on top of the SnakeFile (This can be done using same Seamleass macro, which may take an OUTPUT as an optional input).
Alternatively, the rule may selectively extract specific clusters. In that case, 
Snakefile 2 itself is static, but must be invoked with a list of target files 
rather than a target rule. This list of target files is what must be generated by
a custom Seamless transformer. (again, the same macro can execute it) 
Snakefile 3 generates clusterX.stat and clusterX.log for every cluster X. Snakefile 3
is static, but has a dynamic number of inputs and outputs. Again, you have the choice
between generating OUTPUTS or generating the target files.
In all cases, the macro offers the option to pass either individual "files" in separate input pins, or to pass in a whole filesystem-like JSON, creating a binding for each input "file". The output is always a filesystem-like JSON.
Long-term improvements:
- Support SnakeMake run-functions  (Python code using the SnakeMake API) within rules, inside a static DAG.
- Support for SnakeMake inputs/outputs that are a file list, rather than a single file.

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

Undo
====
NOTE: seamless will never have any global undo system. It is up to individual editor-reactors to implement their own systems.

Plugin-socket connection system 
===============================
Spooky effects at a distance.
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
Plugins/sockets will be named by keys. You can hard-code the keys or send them as cells.
This system is obviously only for impure reactors. They are allowed to modify editpins as a result,
 but never outputpins.
Signals and callbacks will be implemented as part of the same system. 


Why Seamless is not dataflow or Functional Reactive Programming
===============================================================
- "History doesn't matter". Dataflow and all flavors of RP react to 
   event streams that produce and consume in real time.
  In this sense, Seamless is most akin to a spreadsheet.
- "Code is just another kind of data". Dataflow and FRP all assume the code as a given.
- Unlike dataflow (but like FRP), Seamless is really strict about determinism 
  (purity, referential transparency etc.)
- "Always resubmit your entire computation."
  Seamless is very fanatical about caching. If you really want to react to event streams, 
   just give it an initial value, e.g. [E1, E2, E3], and feed it into a Seamless cell. 
  When a new event E4 comes, just replace the cell value with [E1, E2, E3, E4]. 
  Seamless will model it just as if it was [E1, E2, E3, E4] all along (history doesn't matter).
  But in most of the cases, it will re-use the computations that were done before,
   instead of recomputing from scratch.

Theoretical insights
====================
Seamless is an inter-Turing language. It focuses on decomposing a program that is
Turing-complete into components.
It is not about *concrete* decomposition, which concerns itself with reusability,
 code clarity, etc. (this is a software engineering thing)
Rather, it concerns itself with *abstract* decomposition, i.e. how to define 
 elegant primitives of which any program can be composed. Composition is using a call graph.
Programming languages do this also, but there, the primitives are not Turing-complete,
 only the composition is.
In contrast, Seamless is an inter-Turing language: it is about composing primitives that are by themselves already Turing complete. An inter-Turing language is concerned about the syntax and semantics of dependency graphs, and is completely disjoint from the syntax of the primitives. The primitives have their own namespace (Turing tape),
which must be explicitly connected by the inter-Turing language. Seamless has a universal primitive for data transformation, which models source code as just another data input. It does not prescribe a syntax for this source code: any programming language can be used, as long as its execution has referential transparency. Seamless does not enforce this, violation simply leads to undefined behavior. 
Similar languages: Linda, Data flow programming, Notebooks.

Seamless is purely functional, reactive and interactive
Purely functional => determinism and referential transparency, and side effects don't matter
Interactive: You can modify the call graph while it is being executed
Reactive: Seamless automatically reacts to changes

Bash is inter-Turing and somewhat interactive, but not functional.
Notebooks are interactive and somewhat inter-Turing: however, they share the same code namespace and variable namespace, unlike Bash. Magics can be used to regulate this.
Neither Bash nor Notebooks are reactive. Since they are imperative, re-execution is expensive.
GHCI is interactive but not inter-Turing and not reactive: if you re-define a function, expressions do not get updated. Therefore, while Haskell is functional, GHCI is not functionally reactive.
Spreadsheets are functionally reactive and interactive.
purely functional in the sense that they connect the cells and 
 insert their values into the cell code.
Cell code itself is imperative (for Excel: Visual Basic)
Spreadsheets are not truly inter-Turing because they share the same code namespace
 (like Notebooks)
***Insight***: functional + reactive + caching makes trivially interactive: just re-evaluate the call graph every second!
Gnu Make (and SnakeMake) is inter-Turing, functional and reactive (and trivially interactive)
Still, it is a bad (de)composition tool because it composes binaries that have been compiled and installed. No access to the compilation Makefiles of those binaries, or to the installation scripts (which can be in a functional language, e.g Nix).
So you cannot decompose a Makefile all the way down to the source code of the
 individual binaries. This is only OK if the binaries have a formal spec regardless
 of implementation (POSIX), otherwise it is not portable/reproducible.
File modification time as a proxy for true (checksum-based) reactivity, bad!
Worse: files can be modified externally, breaking determinism.
Dataflows are bad because they treat data and code differently.
Dataflow frameworks are often reactive towards data cells, but never towards code.
I know of no dataflow framework that allows interactive programming with
 separate namespaces for each code cell (inter-Turing).
Things like Galaxy are somewhere halfway between (Snake)Make and dataflow, sharing
 at least some of the vices of each.

Notebooks are bad because there *are* no data cells, only code cells.
Typically, there is only one namespace, and typically, the call graph is
strictly linear.
Spreadsheets are bad because they mix composition syntax (purely functional) 
 and evaluation syntax (imperative) and have a single code namespace.
 This makes it very hard to make polyglot spreadsheets.
Seamless has a strong opinion about what it means to assign a cell's value.
It is either an *evaluation assignment*, which means that it happens *once*,
or an *authority assignment*. Assignments are constant.
Seamless *cells* are not constant (in the sense that variables in functional 
programming and mathematics are constant) but Seamless *checksums* are.
Therefore, evaluation assignment happens once, but Seamless reacts to
 *authority assignment*, which is: changing a cell that is not the output of
an operation. Authority assignments can happen from the terminal, over the network
(shareserver), or from a reactor. Seamless treats them all the same. An authority
assignment discards the previous value of a cell, a cell's history is not modelled.
This is the same as a spreadsheet, but different from FRP and reactive frameworks in imperative languages, which explicitly model the dynamic behavior of values (as event streams).
Seamless is also a functional language in the what-not-how sense. Let's take for example a piece of Python code "result = sorted(table)".
This can be applied to a simple array cell ctx.table, with a 2D Numpy array. But ctx.table could also be a deep cell may span terabytes,
 with each fragment checksum cached at different remote locations. In that case, it makes perfect sense for a Seamless implementation to
 interpret "result = sorted(table)" as a Spark query. ctx.table can be converted to a Spark RDD on the fly, or it may already be a persistent
 RDD, identified by a checksum-to-RDD cache server. The result will then be converted back from an RDD to another deep cell (using caching), or to a normal array cell (using a Spark action). Seamless does not care, since in terms of checksum calculus, the result is the same
 (except of course that deep cells do not have a single checksum describing the whole data, but a framework like Spark could compute one).
