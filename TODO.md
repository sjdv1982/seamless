Great Refactor is underway (see seamless-towards-02.md).

Part 1 is now complete

Things to do:

Part 2: high level
  - low-level structured cell editchannels  
  - Reactors
  - Constructors
  - Test indirect library update system, also with constructors
    Test library-containing-another-library
    Copy depsgraph when copying contexts!
  - Edit schema JSON as file (proper mounting)
  - C/C++ cell translation
    (Transformer gains .compile_options, .link_options, .header (read-only),
     but only if language is C/C++)
  - Serialization
  - Cloudless proof-of-principle  

Part 3 (low-level / cleanup):   
   - Signals (DONE; only to test)
   - Observers (subclass of OutputPinBase)
   - Add back in int/float/str/bool cells because they are so convenient.
     Their content type will be int/float/text/bool.
     Adapters will convert among them (e.g. int=>float) and between them and JSON/mixed/text.
     Supported access modes are JSON and text. Adapters will convert to Silk.
   - Terminology: context children can be private, in which case they are not in __dir__.
     By default, they are public. No more "export".
     This has nothing to do with services. Services determine private and public based on
     what connects into the serviced context.
   - Have a look if Qt mainloop hook can be eliminated.
   - equilibrate() should not wait for workers with an execution error
   - Start with lib porting. Port Qt editors (including HTML), but no more seamless.qt
     Port all macros, but store the code in plain Python modules in lib, that register a library context
   - Port websocketserver, with proof of principle
   - Port OpenGL, with proof of principle
   - Cleanup of the code base, remove vestiges of 0.1 (except lib and tests).
   - Cleanup of the TODO and the documentation (put in limbo)

Merge into master? With direct mode, most tests should work now? Other ones can be ported...

Part 4 (low-level):   
  - Terminology: authority => source. "only_source" option in mounting context, mounting only source cells
  - Report cells (JSON cells, can become structured if directed from the mid-level).
    Status dict becomes a a Report cell.
  - Log cell: text cell to which an observer can be attached that receives new entries)
     The result of translation, caching, macros, etc.; generalized log API.
     Even transformers and reactors may be declared as having a log output, and various loglevels
      (transformer.py will already send low-priority log messages about receiving events etc.)
  - Finalize caching:
    - write cache hits into a Log cell
    - structured cells: outchannels have a get_path dependency on an inchannel
    - structured cells: calculate outchannel checksum (see remarks in source code)
    - re-enable caching for high level (test if simple.py works now)
    - reactors: they give a cache hit not just if the value of all cells are the same, but also:
           - if the connection topology stays the same, and
           - the value of all three code cells stays the same
       In that case, the regeneration of the reactor essentially becomes an update() event
  - Lazy evaluation and concretification (see below)
  - Silk form validators
  - Silk: error messages, multi-lingual (use Python format() syntax, but with properties to fill in, i.e. "The value cannot be {a.x}". This is natively supported by Python. No magic in the style of {a.x+a.y}; define a property for that)
  - Seamless console scripts and installer


Part 5: shift to the mid-level data structure
- Sovereignty
Mostly elide the middle level, dynamically generate at time of low-level generation/serialization.
The middle level is the input of a translation macro, whereas the low level is the output
Normally:
1. Being under macro control, the lower level could never be authoritative
2. Any changes to the mid-level would re-trigger the translation macro.
=> Introduce an exception: sovereignty
A low level cell may be sovereign if it has a 1:1 correspondence to a mid-level element.
Sovereign cells are authoritative, they may be changed, and changes to sovereign cells do not cause
the translation macro to re-trigger.
When a translation macro is re-triggered for another reason (or when the mid-level is serialized),
the mid-level element is dynamically read from the sovereign cell (no double representation)
- Expand mid-level graph syntax (see seamless-towards-02.md):
  - reactors
  - macros (by definition low-level) with language (python) and api (pyseamless) fields.
  - signals
  - add operators (but only those) UPDATE: implement at high-level (wrapper around transformer, but not an operator)
  - no observers; not sure about mount.

Part 6: applying the mid-level. Some of this can be delayed until post-merge.
- Ephemeral cells. Also nice for a transformer to store partial results
  Apply this to slash0
- Reconsider the restrictions on transformers and reactors. Give transformers
  edit pins and cache pins, allow them to have reactor pin API.
  At least in theory, allow transformers/reactors to declare as sync/async, and thread/process.
  In the same vein, transformers should be able to be declared as "immediate", which means:
  sync and activated during translation / macro construction.
  (Macros are also "immediate" workers already).
  This allows a macro to depend on an immediate transformer, to avoid async macros (= cache misses).
- Preliminary outputpins (in transformers [as secondary output] and in reactors)
- Preliminary inputpins (pins that accept preliminary values). Right now, all inputpins are preliminary!
- Equilibrium contexts (see below)
- finalize the design of mid-level graph syntax.
  - Include old 0.1 resources, or make this high-level only?
  - Save high-level syntax as mid-level only, or separately?

Part 7, the high level :
OUTDATED, since a lot of it is done now. No high-level macros, since constructors will suffice!
- High-level syntax, manipulating the mid-level graph. Syntax can be changed interactively if Silk is used.
  Proof of principle DONE. TODO:
  - mounting is not quite satisfactory (redundant "translated" context)
  - Reactors; Edit schema JSON as file (proper mounting) => Reactor for JSON <=> CSON (JSON is written as CSON cell, CSON cell edits JSON)
  - Many usability issues
  - Translation policies (these are auxiliary)
  - Syntax customization (see seamless-towards-02.md).
- High-level extensions of serialization (e.g. take care of reporting, shells... Do we need this? or midlevel only?)
The rest of part 6 could be delayed until post-0.2
- High and low policies like .accept_shell_append should go into a cell
- Meta-schema for schema editing (jsonschema has it)

NOTE: for the high level, something clever can be done with cells containing default values; these cells are only connected to a structured_cell
if the structured_cell has no other connection (for that inchannel, or higher). This connection is dynamic (layer).

NOTE: seamless will never have any global undo system. It is up to individual editor-reactors to implement their own systems.

Part 8 (pre-merge):
- Port over 0.1 lib: from .py files to Seamless library context files. (can be delayed post-merge?)
- Port over 0.1 tests

Part 9 (merge):
  Port over Orca and other examples
  Make new videos:
    - Basic example
    - Fireworks
    - 3D
    - Docking
    - Orca (don't show the code)  

RELEASE as 0.2.

Post-merge, post-release (0.3):
- Replace the use of killable threads with processes... gives a problem with Orca example (fixed now ?), docking example (?), see Github issue
- Bidirectional cell web editing via Websocketserver
  (also HMTL gen from schema)
- REST API (alternative for Websocketserver)
- Web service JSON API (to provide all parameters in one go)
- Old-school CGI API (alternative for web service JSON API)

0.4:
- Re-integrate slash0, apply ephemeral cells to it

0.5
- C/Fortran/CUDA/OpenCL integration (BIG).
  - Requires also a Silk extension (GPU storage, fixed-binary, see silk.md)
  - IPython (.ipy)/Cython magic is not (or barely) necessary, since IPython is natively supported by workers.
- Blocks
- Bags

0.6
- Sync mechanisms / collaborative protocol
 ("virtual context" that upon creation syncs topology from another context, and then
  bidirectionally syncs the cell values; REST or Websocketserver under the hood)

Post-0.6:
- Address shell() memory leak: IPython references may hold onto large amounts of data
- Expand and document seamless shell language (slash)
- Special high-level authority syntax for library contexts (fork into libdevel)
- Add "version" to "language" (both for code cells and for Silk).
  To evaluate properly, major version must be exactly that; minor version must be at least that.

Long-term:
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
  the designated result cells. Depending on additional

- Reactor start and stop side effects (see below)
- The seamless collaborative protocol (high level) (see seamless-towards-02.md)
  This replaces the websocketserver with a Crossbar WAMP server.
- Delegated computing with services, evaluation cells
  (BIG!, see seamless-towards-02.md:
    - "Towards flexible and cloud-compatible evaluation"
    - "Network services"
    - "The web publisher channels")
- Set up user library directory and robogit
- Python debugging / code editor (WIP) / unit tests (see seamless-towards-02.md)
- Other mount backends (databases)
  As a variation, an option for cells to have no .\_val, i.e. .value always pulls
   the value from the backend (it is assumed not to have changed!)
   UPDATE: use concretification instead
- Full feature implementation of Silk, e.g. constructs (see silk.md)

Very long-term:
- Other implementations? JavaScript? Erlang? Elixir? Go?
- Equilibrate/unstable overhaul (test on Collatz test)
- "Activate" overhaul, the onion of Python with statement make it slow (test on Collatz test)
- GPU-GPU triggering
- Re-implement all high level classes as Silk classes with methods in their schema.
- Organize cells into arrays (probably at high-level only)
- Cells that contain (serialized, low-level) contexts. May help with faster caching of macros.

Auxiliary, ephemeral and execution cells
========================================
Execution cells are cells that contain only execution details and do not influence the result.
  Examples: number of CPUs, temp directory where to execute slash in, caching locations
Ephemeral cells are the same, but they indicate some hidden dependency.
  Examples: session ID, temporary file name, file with pointers in it (ATTRACT grid header)
  A reactor may have an editpin to an ephemeral cell, used for caching.
Ephemeral cells must be lazy, they cannot be stored, and they are not authoritative.
Changes in execution cells or ephemeral cells do not trigger re-computation, but the worker
 will receive the new value once something else triggers re-computation.
Auxiliary cells/contexts are high-level only. Auxiliary cells (like ephemeral cells and
  execution cells) are stripped from a high-level graph before its grand computational checksum
  is computed.


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

Concretification
================
"Concretification" is a feature that cells may not need to store their full value.
It involves sending two signals upstream, i.e. a cell's input pin or inchannels
that requests something from the upstream worker or cell.
1. send my hash/checksum
2. (re-)send again my value
Applications of this are in:
- blocks (with compression; see below),
- backend caching (a cell may just store its hash and demand its value when needed from
   a cell server; if the server fails, it may send a signal 2.)
- lazy evaluation (in lazy mode, transformers evaluate only upon receiving a signal 2.
Reactors and macros send a signal 2. to each of their input cells
3. Release. In case of lazy cells, signal 2. is non-blocking; the manager is notified when
 the result is ready. The manager then forwards the results, and sends back a "release" signal,
 meaning that the value may be freed from memory. If this indeed happens or not, depends on
 the configuration (although compressed blocks always free).
 The checksum of the cell always kept. The value may still be in a checksum cell server.
 If the value cannot be retrieved, a signal 2. is sent upstream.
 (Non-lazy cells may also rely on such a server, but in their case, it is an error if the server fails.)


Equilibrium contexts
====================
Transformers are guaranteed not to send anything (be it cell values or events) on their primary output until execution has finished (which means they are in equilibrium).
In addition, transformers are guaranteed not to accept any events while not in equilibrium. If there are any,
 the transformer computation is actually canceled.
This is obviously not so for reactors, and it is also not so for contexts that contain reactors (or multiple transformers that are not arranged linearly) connected to exported outputs of the context.
It is possible to declare contexts as "equilibrium contexts". In that case, they have the same guarantees as transformers have: sending cell updates or events to the outside world is delayed until equilibrium is reached, and so is the acceptance of new events. This allows contexts to perform atomic computations, reducing the number of glitches.
It is possible to declare some of the outputs as "secondary", which means that they escape this guarantee (for example, for logging purposes).
"Events to the outside world" is only restricted if it goes through exported cells and pins. Traffic through
non-exported objects is not restricted.

Application to ATTRACT: the mainloop reactor
============================================
Because of the cylic dependency, an energy minimization loop is not a good fit for Seamless. But it can be done.
There must be an ATTRACT mainloop reactor with editpins A and C, and inputpins B and D.
Pin A contains the DOFs: upon start-up, it is copied from the initial DOFs.
It is assumed that a "scorer" context listens to A and gives results on B, which is the energy and DOF gradients.
To activate the scorer, the mainloop reactor sets A, then equilibrates A and B, then reads B.
Pin C also contains the energy and DOF gradients, and D also contains the DOFs
It is assumed that a "minimizer" context listens to C and then gives results on D.
To activate the minimizer, the mainloop reactor sets C from B, then equilibrates C and D, then reads D.
The scorer can then be re-activated by setting A from D.
The minimizer and scorer contexts must be equilibrium contexts.
"Equilibrating" is done by a having a signal that fires when a context reaches equilibrium.
 Use "on_equilibrate" hook of root managers (adapt for non-root).
The ATTRACT mainloop reactor will have two signal inputpins for this (from scorer and minimizer) and an internal
 variable that maintains which signal is to be listened for.
A and C are cached together with the number of minimization steps that have been performed. In this way:
- The mainloop context can be saved in mid-evaluation and resumed later
- The number of steps can be increased and only the additional steps are computed.
Equilibrium contexts should also have a Report cell that reflects the checksum value of all exported cells and pins
that are "input".
Exported cells are "input" if they are authoritative within the cell. Exported pins are "input" if they are inputpins.
The mainloop reactor will listen for these checksum Report cells; when they change, the whole computation must be restarted.
When porting ATTRACT, the minimizer and scorer should be in slash.

Thoughts on Seamless and purity
===============================
Seamless workers must be pure in terms of cells: given the same input cell values, they must always produce the same final output
 cell values. This precludes the use of random generators, system time, or even the opening of an external file or URL.
Special input cells, Evaluation cells, do no count as input cell values.
This formulation of purity gives the following liberties:
 - Workers are allowed to produce different non-final (preliminary) cell values (TODO: mark them as such)
 - They are allowed to have arbitrary side effects, as long as one of the following is true:
   - These side effects do not concern output cells
   - Or: they are idempotent in terms of input cells.
   For example, a transformer may open a GUI showing a progress bar (although a preliminary cell would be cleaner)
   Or, a reactor may compute the checksum of its inputs, store this in a database, and later retrieve the checksum and use it
    to produce the output.
 - They are allowed to send arbitrary values to special cells called Report cells (that reflect the status) and Logging cells
   (that accumulate values).
 - They are allowed to change cells via edit pins. This is considered an "act of authority", as if the programmer himself had
    changed this cell.

Blocks
======
In Seamless, workers are expected to send values, for which they allocate the memory themselves.
Blocks are a (low-level) mechanism to pass around pre-allocated buffers of fixed size.
This mechanism can save memory, but more importantly, it is much more compatible with GPU computing.
Memory is not copied back-and-forth by every worker. Instead, buffers reside permanently on the GPU.

A block description consist of dtype, shape and namespace. It is always C-contiguous in memory.
An extended block description includes stride and offset.
Namespace can be "cpu", "opencl", "opengl" or "cuda". Maybe in the future, new namespaces can be registered.
Block allocation can happen in two ways:
- Via an Allocator (new low-level construct). The block descriptor must be given to the allocator constructor.
  The Allocator provides an allocator output pin, which gives both the block descriptor and the allocated buffer.
- Via a StructuredCell, in Silk mode. The path of every allocation must be declared in "allocators", which works
  similar to "outchannels": each path becomes an allocator output pin.
  From the shell, the allocation path value is readable (resulting in the block value, copied to a Numpy array)
  but not writable. No inchannel or outchannel may be a superpath of the allocation path (at the high level, this
   must be checked during assignment, before translation).
  The StructuredCell must have all block descriptors declared during construction, including namespace.
  However, for high-level cells, the block descriptor is read from the .schema. In any case, if there is a schema
   entry, the StructuredCell will check that it is compatible with the block descriptor.
  When the OverlayMonitor (or its subclass) is created, a buffer is created (in the appropriate namespace)
  using the block descriptor, and when activated, both are sent over the allocator output pin.
Blocks can only ever be written to through a BlockManager.
The block descriptor must be given to the BlockManager constructor. The BlockManager provides an allocator input pin,
 which must be connected to an allocator outputpin.
The BlockManager exposes a block inchannel and a block outchannel. Workers can declare their own block outputpins to
 write to the block inchannel. Once a worker has written there, the BlockManager will fire on the outchannel.
 Workers can declare their own block inputpins to receive Block outchannels.
 When the BlockManager is constructed, each Block inchannel and outchannel sends a signal. This signal contains a unique
  BlockManager ID, and an extended block descriptor. Workers must verify that input blocks and output blocks do not
  overlap in memory (see numpy.shares_memory and Diophantine equations), which is illegal.
 Whenever the BlockManager is allocated, each Block inchannel and outchannel sends another signal, which contains the
  pointer itself.
 Whenever a worker has set a block outputpin (i.e. when it is done modifying it), it sends a signal containing the checksum of
  the block content. Likewise, it receives such a checksum on its inputpin.
 Whenever a BlockManager receives checksum updates on its inchannel(s), it computes and stores checksum updates over
  its outchannels.
 A BlockManager may define one *tiling shape* and many *tiling channels*.
 A tiling shape is like an array shape ("length" for each dimension). Length must be a divisor of the
  number of elements for that dimension. The block is tiled over "length" tiles in that dimension,
  and the memory is divided equally over each block.
   A tiling channel can be inchannel or outchannel, they works exactly like StructuredCell channels, but instead of
   property paths, they contain index paths (although if referencing a struct array, the last few elements
   of the index paths may be properties). Only single indices: ranges and steps are not supported.
   As for StructuredCells, it is checked that the inchannels and outchannels do not overlap.
   This is a way to process parts of the buffer independently.

 BlockManagers can be lazy, in which case all inchannels and outchannels are lazy.
 BlockManagers own their data, and have a special method to have it set programmatically at startup. (It is copied onto the
  allocated block later, after the allocation pin has fired)
Caching of dependencies through BlockManager has to go in the same way as StructuredCell, i.e. with some difficulty.
 When GPU-GPU triggering will be implemented, it will be using an API on blocks / tiles, together with concretification.

Bags
====


Special constructs
==================
These are special constructs with generic application, as they use serialized high-level graphs.
Each special construct has a reference implementation. The checksums of the
 reference implementation code are always considered as ground truth.
They can be executed as every other non-interactive Seamless service in this way.
However, services may offer to accept special construct requests, but process them
 with a very different optimized implementation under the hood.


- Map

- Reduce

- CyclicIterator
Performs a fixed number of iterations of a cyclic graph.
Requires a serialized high-level graph g that performs the computation
There must be the fixed number of iterations N.
There must be an iteration variable: a variable that has an initial value, and
 where the result of the computation becomes the input for the next computation.
There may be multiple such iteration variables (although there is only one loop).
Each variable can be indicated as "accumulate" or "last". "last" keeps only the last value.
"accumulate" accumulates into an array or a Block.
Reference implementation:
- Allocate an array or Block for every accumulated itervar
- Allocate input cells for input
- Allocate output cells for every itervar
- Translate the graph, connect it to input and output cells
- Assign the (initial) input values to the input cells, and equilibrate.
- For N iterations: read the itervars from the output cells. Accumulate if needed.
- If not the last iteration: write the itervars to their input cells, and equilibrate.
- Return the itervars (accumulated or not)

- Sort
Converts a Bag to a Block or an array cell.
Retrieves all the keys of the Bag. Sort the keys and build a Block with the indices.
Demand all values in parallel.
Either return a lazy Block, or wait for all values and return a normal Block or array.

- Filter
Like Map, but this time the graph must return a boolean (keep it or not).

Cyclic graphs
=============
Strategies to model them:
1. Don't model cycles with seamless (keep cycles inside a single worker)
2. Explicit cells for every assignment (if number of iterations is known).
   First assignment to cell x becomes cell x1, second assignment to cell becomes x2, etc.
   Automatic parallelization, but very space-intensive!
3. Use an CyclicIterator (see Special Constructs). if number of iterations is known.
   Build a high-level graph g that performs the computation, and send it as data   
4. Use a reactor + editpins (see ATTRACT mainloop application)
5. Nested asynchronous macros (but seamless will warn of cache misses, and
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

Lazy evaluation
===============
Lazy cells are cells that are marked as such. They must be dependent on a
 transformer.
Reactors immediately concretify all of their lazy inputs, and cannot have a
 lazy output/edit.
However, transformers that output lazy cells automatically become lazy.
They concretify their inputs only when its output cell becomes concretified.

An important advantage of lazy cells is that there are stronger timing guarantees.
Signal 2. (invalidate the value) is propagated forward *immediately* by Seamless
 towards downstream dependencies (stopping transformers in their tracks), before
 sending any values to the workers.
Example: dependency graph A=>B, A=>C, B+C=>D. If A is updated to A*,
 B will become updated to B* and C to C*.
 Eventually, D will be evaluated from B*+C*, but the intermediate computations
 B*+C or B+C* are both possible as "glitches". However, if B and C are lazy, then
 an update for A will immediately invalidate them, and the glitches disappear.
From the Python shell, lazy cells have a method that concretifies in a non-blocking manner.
In addition, they have a method that concretifies in a blocking manner
 and then returns a result.
Finally, they have a channel that sends concretification signals,
 to which Python can subscribe callbacks (like an observer or Hive push antenna)

In addition to LazyCell, there is LazyCallback, which emulates LazyCell.
However, a LazyCallback wraps a zero-argument Python callback (blocking or non-blocking)
 into a cell value. This callback is triggered upon concretification.
With cffi, the callback can come from another language, like C or even Haskell.
Note that callback foo cannot be serialized, it is the responsibility of
 Python (or whatever host language) to bind the callbacks after graph instantiation.


Workers and memory
==================
By default, workers keep all of their values buffered. This may eat up a lot of
 memory resources. Pins may be configured to be on-demand instead. In that case,
 seamless will send only the checksums, and the worker will then have to ask for
 the value.
 In case of transformers/macros, this is a single request for all of the values.
 For reactors, the request is actually made when the pin value is demanded.
 This request is blocking, so it should probably only be used for async reactors.


Control over side effect order
==============================
This can be done using Hive.
- Cells are exposed to Hive as push inputpins.
  Hive push outputpins are exposed to Seamless as outputpins.
- Signals are exposed to Hive as push trigger inputpins, and vice versa.
- Lazy cells are exposed as pull outputpins. The Hive pull leads to a concretification.
  Likewise, Hive pull outputpins are exposed as lazy cells.

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
