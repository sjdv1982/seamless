Great Refactor is underway (see seamless-towards-02.md).

A proof-of-principle of the middle/high level is now there.

Things to do:

Part 1 (low-level):
   - Redesign the transfer protocol (copy, ref etc.).       
     - When negotiating the transfer protocol/making adapters:
       - Loop over the cell supported modes; one of them must succeed.
         In case of cell-cell, loop over source; within that, loop over target
       - If transfer mode is "ref" or "buffer" and it doesn't work, try "copy".
       - An access modes like "silk" is never directly supported, it must be added via adapter
     - Expand adapters, and expand negotiation to cell-pin and pin-cell.
     - Remove (from deserialize and serialize) support for modes that are no longer declared in supported_modes
       (e.g. Silk support)
     - Expand and test the CSON example, especially test only_text; test only_text also for Python cells
   - Add the concept of from_pin (from_channel) to structured cells, in particular the form/data/storage hooks. Now,
   they trigger warnings that they are overruling cells "controlled by Seamless context"
   (see tests/highlevel/simple.py). This is distinct from sovereignty, which involves non-pin manipulation!
   - "Active" switch of managers, workers, connections; may also be exported, and may be activated in a connection layer.
      UPDATE: done for managers. Extend to workers (transformers and reactors) as well. YAGNI for connections.
   - PyModule cells and code injection (PyModule cell becomes a Python module).
     Also PyCompositeModule which will have inputpins that are PyModules.
     All PyModules will be transported as source to the worker, where they will be built into code.
     UPDATE: injection will be a mid-level concept.
     At the low-level, it will just be pins declared as "module", with a submode that contains import parameters, and
     a language "python" or "ipython".
  - PyModules must have native IPython support. Need IPythonCell for that reason! Add support to transformers and reactors! Not for macros.

Part 2 (low-level / cleanup):   
   - Signals (DONE; only to test)
   - Observers (subclass of OutputPinBase)
   - Add back in int/float/str/bool cells because they are so convenient.
     Their content type will be int/float/text/bool.
     Adapters will convert among them (e.g. int=>float) and between them and JSON/mixed/text.
     Supported access modes are JSON and text. Adapters will convert to Silk.
   - Have a look if Qt mainloop hook can be eliminated.
   - Start with lib porting. Port Qt editors (including HTML), but no more seamless.qt
     Port all macros, but store the code in plain Python modules in lib
   - Port websocketserver, with proof of principle
   - Port OpenGL, with proof of principle
   - Cleanup of the code base, remove vestiges of 0.1 (except lib and tests).
   - Cleanup of the TODO and the documentation (put in limbo)

Merge into master? With auto_macro_mode, most tests should work now? Other ones can be ported...

Part 3 (low-level):   
   - Dynamic connection layers: a special macro that has one or more contexts as input (among other inputs), which must be (grand)children
      Like static layers, they are tied to a macro or toplevel context
      They take as input any children of the context (cells or child contexts);
      Builds connections within/between those children. May set active switch as well.
      They can never build new cells, use the help of a macro for that.
      The result layer consists of a set of pairs (connection + callback that removes that connection),
       and (object, newstate, oldstate) for objects that have been activated/disactivated.
      Dynamic connection layers will always be evaluated after any other fprward update.
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
    - implement successors (YAGNI?)
    - write cache hits into a Log cell
    - structured cells: outchannels have a get_path dependency on an inchannel
    - re-enable caching for high level (test if simple.py works now)
    - reactors: they give a cache hit not just if the value of all cells are the same, but also:
           - if the connection topology stays the same, and
           - the value of all three code cells stays the same
       In that case, the regeneration of the reactor essentially becomes an update() event
  - Silk form validators
  - Silk: error messages, multi-lingual (use Python format() syntax, but with properties to fill in, i.e. "The value cannot be {a.x}". This is natively supported by Python. No magic in the style of {a.x-a.y}; define a property for that)
  - Seamless console scripts and installer

Part 4: shift to the mid-level data structure
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

Part 5: applying the mid-level. Some of this can be delayed until post-merge.
- Cache cells. Also nice for a transformer to store partial results
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

Part 6, the high level :
- High-level syntax, manipulating the mid-level graph. Syntax can be changed interactively if Silk is used.
  Proof of principle DONE. TODO:
  - mounting is not quite satisfactory (redundant "translated" context)
  - Macros
  - Reactors
  - Many usability issues
  - Translation policies
  - Syntax customization for library contexts (see seamless-towards-02.md).
- serialization (take care of shells also). (Do we need this? or midlevel only?)
- high-level macros. They contain high-level syntax.
  They have, as an extra input, (a copy of) the high-level translation policies that were in effect at the time of creation
The rest of part 5 could be delayed until post-0.2
- High and low policies like .accept_shell_append should go into a cell
- Meta-schema for schema editing (jsonschema has it)

NOTE: for the high level, something clever can be done with cells containing default values; these cells are only connected to a structured_cell
if the structured_cell has no other connection (for that inchannel, or higher). This connection is dynamic (layer).

NOTE: seamless will never have any global undo system. It is up to individual editor-reactors to implement their own systems.

Part 7 (pre-merge):
- Port over 0.1 lib: from .py files to Seamless library context files. (can be delayed post-merge?)
- Port over 0.1 tests

Part 8 (merge):
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
- Special high-level authority syntax for library contexts (fork)

Long-term:
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
- Event streams (BIG!)
- Full feature implementation of Silk, e.g. constructs (see silk.md)
- Lazy evaluation, GPU-GPU triggering (BIG!)
- Re-implement all high level classes as Silk classes with methods in their schema.
- Organize cells into arrays (probably at high-level only)
- Cells that contain (serialized, low-level) contexts. May help with faster caching of macros.
- ATC chains with folding/unfolding (YAGNI?)

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
