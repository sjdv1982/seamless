Great Refactor is underway (see seamless-towards-02.md).

Part 1 is now complete

Things to do:

Part 2: high level  
  - .\_lib => libcell during translation
  - Context copy
    UPDATE: rip the copiers and constructors, high-level macros should be enough!
  - Libraries
    .\_lib attribute means that upon translation, an equilibrate hook is added
     when the hook is activated, the cells in the translated context are lib-registered
      (see low-level library)
  - High-level macros
  - Indirect library update (see Library.py)

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
   - Dynamic connection layers: a special macro that has one or more contexts as input (among other inputs), which must be (grand)children
      Like static layers, they are tied to a macro or toplevel context
      They take as input any children of the context (cells or child contexts);
      Builds connections within/between those children.
      They can never build new cells, use the help of a macro for that.
      The result layer consists of a set of pairs (connection + callback that removes that connection),
      Dynamic connection layers will always be evaluated after any other forward update.
      Therefore, if you have A => macro => B, A + B => dynamic layer, you can assume that the macro
       will respond first to changes in A, so that B will reflect the new A.
  - Terminology: authority => source. "only_source" option in mounting context, mounting only source cells
  - Report cells (JSON cells, can become structured if directed from the mid-level).
    Status dict becomes a a Report cell.
  - Log cell: text cell to which an observer can be attached that receives new entries)
     The result of translation, caching, macros, etc.; generalized log API.
     Even transformers and reactors may be declared as having a log output, and various loglevels
      (transformer.py will already send low-priority log messages about receiving events etc.)
  - Finalize caching:
    - implement successors (YAGNI? now that the low-level is subordinate, better rip them)
    - write cache hits into a Log cell
    - structured cells: outchannels have a get_path dependency on an inchannel
    - structured cells: calculate outchannel checksum (see remarks in source code)
    - re-enable caching for high level (test if simple.py works now)
    - reactors: they give a cache hit not just if the value of all cells are the same, but also:
           - if the connection topology stays the same, and
           - the value of all three code cells stays the same
       In that case, the regeneration of the reactor essentially becomes an update() event
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
  - add operators (but only those)
  - no observers; not sure about mount.

Part 6: applying the mid-level. Some of this can be delayed until post-merge.
- Cache cells. Also nice for a transformer to store partial results
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
- High-level syntax, manipulating the mid-level graph. Syntax can be changed interactively if Silk is used.
  Proof of principle DONE. TODO:
  - mounting is not quite satisfactory (redundant "translated" context)
  - Macros
    In high-level macros, assigning to a (lib) Context creates a dependency!!
  - Reactors
  - Many usability issues
  - Translation policies
  - Library construct (easy enough, but think of serialization)
  - Syntax customization (see seamless-towards-02.md).
- serialization (take care of shells also). (Do we need this? or midlevel only?)
- high-level macros. They contain high-level syntax.
  They have, as an extra input, (a copy of) the high-level translation policies that were in effect at the time of creation
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
- Re-integrate slash0, apply cache cells to it (see mount.py:filehash)

0.5
- C/Fortran/CUDA/OpenCL integration (BIG).
  - Requires also a Silk extension (GPU storage, fixed-binary, see silk.md)
  - IPython (.ipy)/Cython magic is not (or barely) necessary, since IPython is natively supported by workers.
- Address GLstore memory leak: stores may not be freed (is this still so post-0.1 ??)

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
- Reactor start and stop side effects (see below)
- Concretification (see below)
- Blocks (see below)
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
- Event streams (BIG!)
- Full feature implementation of Silk, e.g. constructs (see silk.md)

Very long-term:
- Other implementations? JavaScript? Erlang? Elixir? Go?
- Equilibrate/unstable overhaul (test on Collatz test)
- "Activate" overhaul, the onion of Python with statement make it slow (test on Collatz test)
- Lazy evaluation, GPU-GPU triggering
- Re-implement all high level classes as Silk classes with methods in their schema.
- Organize cells into arrays (probably at high-level only)
- Cells that contain (serialized, low-level) contexts. May help with faster caching of macros.
- ATC chains with folding/unfolding (YAGNI?)

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
- event streams (see below)
- blocks (with compression; see below),
- backend caching (a cell may just store its hash and demand its value when needed from
   a cell server; if the server fails, it may send a signal 2.)
- lazy evaluation (in lazy mode, transformers evaluate only upon receiving a signal 2.
Reactors and macros send a signal 2. to each of their input cells; cell.value sends
a signal 2. and does a special equilibrate that only involves its dependency chain)

Event streams
=============
Event streams receive event values, or a "undo" signal, which means that all previous
values are invalid. Event streams may send back a "send again" signal, which means
that they want again all values that were previously sent to them. (This is for example if a transformer adds 5 to an event stream; if 5 is changed to 6, either in a input cell or by a change in the source code, the transformer will send a "send again" signal upstream).
Reactors may choose to cache events so to avoid sending this signal when one of their other inputs changes.
Finally, there are the "initialize" and "disconnect" signals.
Event stream inputpins are in a state where they accept a new value, or they don't. Force-feeding is possible, in that case the values are buffered up by seamless itself.
Workers must always declare explicitly a pin as event stream.
Transformers don't need any change in their code. However, if one or more of their inputs is an event stream, so must be their output (vice versa is not required, but if all inputs are cells, a transformer that has an event stream as output must return a list, which is force-fed into the event stream after sending an "initialize" signal).
Reactors must push/pull new event stream values in an explicit API:
  - blocking waits for it
  - non-blocking essentially sets to event stream input pin to "accept input" (input) or force-feeds (output)
  - By default, input is blocking while output is non-blocking
Event streams can never be authoritative, they must depend on a worker.
NOTE: The trouble won't be the implementation... but event streams have serious consequences for caching!

Equilibrium contexts
====================
Transformers are guaranteed not to send anything (be it cell values or events) on their primary output until execution has finished (which means they are in equilibrium).
In addition, transformers are guaranteed not to accept any events while not in equilibrium. If there are any,
 the transformer computation is actually canceled.
This is obviously not so for reactors, and it is also not so for contexts that contain reactors (or multiple transformers that are not arranged linearly) connected to exported outputs of the context.
It is possible to declare contexts as "equilibrium contexts". In that case, they have the same guarantees as transformers have: sending cell updates or events to the outside world is delayed until equilibrium is reached, and so is the acceptance of new events. This allows contexts to perform atomic computations, reducing the number of glitches.
It is possible to declare some of the outputs (and event stream inputs) as "secondary", which means that they escape this guarantee (for example, for logging purposes).
"Events to the outside world" is only restricted if it goes through exported cells and pins. Traffic through
non-exported objects is not restricted.

Application to ATTRACT: the mainloop reactor
============================================
Without event streams, an energy minimization loop is not a good fit for Seamless. But it can be done.
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
After event streams, the mainloop reactor will be superfluous
 and can be built as a simple context of event stream cell A-D plus connections,
 with an internal counter (event streams must provide this as a Report cell!) to make the B=>C connection conditional.
Equilibrium contexts with an event stream as input will automatically give one as output, and send the proper "undo" signal
 when they change, resetting the stream.

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
 A BlockManager may define one *tiling pattern* and many *tiling channels*.
 A tiling pattern exists of a list of dicts, one for each dimension. Each dict contains the length (positive integer),
  the mode ("split" or "compress"), and optionally "compression". Length and compression must be divisors of the
  number of elements for that dimension, and "compression" must be smaller or equal to length.
  If mode is "split", then the block is tiled over "length" tiles in that dimension, and the memory is divided equally over
   each block.
  If the mode is "compress", the block is tiled *physically* over "compress" tiles, but *logically* over "length" tiles.
  For example, take a block of a million elements, with "length" as 1000 but "compress" as 10. This means that physically,
   the block is divided into 10 tiles of 100k elements, but *logically*, there exists 1000 tiles of 100k elements, for a
   logical array size of 100 million elements. Of those 1000 tiles, only 10 may be physically held in memory.
 A tiling channel can be inchannel or outchannel, they works exactly like StructuredCell channels, but instead of
  property paths, they contain index paths (although if referencing a struct array, the last few elements
  of the index paths may be properties). Only single indices: ranges and steps are not supported.
 As for StructuredCells, it is checked that the inchannels and outchannels do not overlap.
 If only "split" mode is used, tiling is just a way to process parts of the buffer independently.
 However, if "compress" mode is used, the situation becomes more complicated.
 Like event streams, a tiling outchannel then holds a lock, which is released when all (but not really all, see below)
 of its downstream  dependencies are done with it. The number of locks is equal to "compress", the number of physical tiles.
 Each outchannel contains one logical tile (in "split" mode, an entire dimension may be selected, but this cannot
  work in "compress" mode) and all outchannels compete for the locks. An outchannel will seize a lock when one of its
  dependencies sends a concretification signal 2., and will release it when the dependency is done.
BlockManagers own their data, and have a special method to have it set programmatically at startup. (It is copied onto the
  allocated block later, after the allocation pin has fired)
Caching of dependencies through BlockManager has to go in the same way as StructuredCell, i.e. with some difficulty.
 When GPU-GPU triggering will be implemented, it will be using an API on blocks / tiles, together with concretification.
The domain-specific language "topview" (already used in ATTRACT) will be modified to run on top of blocks.

Cyclic graphs
=============
1. Don't model cycles with seamless (keep cycles inside a single worker)
2. Explicit cells for every assignment (if number of iterations is known).
   First assignment to cell x becomes cell x1, second assignment to cell becomes x2, etc.
   Automatic parallelization, but very space-intensive!
3. Use blocks (if number of iterations is known).
Compressed tiling works well to reduce space requirements.
Example: double a value v 10 000 times.
Declare an BlockAllocator v with 2 elements
Declare a BlockManager b with 10 000 logical elements and 2 physical elements
Declare a code cell c that performs the computation
Declare 10 000 transformers that take b[n-1] as input and b[n] as output, and set the code to c.
(10 000 transformers may still take a lot of space; some way to "put them on ice" with low-mem would be nice)
4. Use a reactor + editpins (see ATTRACT mainloop application)
5. Use event streams (see ATTRACT mainloop application)
6. Nested asynchronous macros (but seamless will warn of cache misses, and
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
Lazy cells are cells that are the output of a lazy transformer.
A lazy transformer becomes active only when its output cell
 becomes concretified.
The transformer concretifies its dependencies only by pin API.
Whenever a non-lazy (or lazy, previously concretified) input
 of a lazy transformer changes, the lazy transformer gets re-evaluated.
Reactors and non-lazy transformers concretify all of their lazy inputs.
Lazy transformers can take foreign-language code cells, by exposing the
 lazy cells as callbacks. This works for C and even for Haskell.

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
This allows Seamless services to be linked in a type-safe manner, amenable to proofs,
  and using the entire toolkit of functional programming (map, reduce, etc.)
Lazy output cq. lazy input cells in Seamless services can be exposed as callbacks-into-Python
 (CFFI supports this) cq. callbacks-into-Idris-functions
 (Haskell FFI at least supports this; Idris FFI does not support closures, that's bad).
