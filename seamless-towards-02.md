*******************************************
GREAT REFACTOR
*******************************************

###
NOTES:
- Only authoritative (or sovereign) cells should be changed from code at runtime.
  Anything else gives a warning, and another warning when restored from a worker.
- Editpins do not lend authority! A cell can have multiple editpins, and an outputpin
  A cell that receives a value from an editpin is as if it comes from code.
- Connection layers: depend on one or multiple contexts (and other inputs) and a code cell.
  Code cell is executed as if a macro, but can only add connections.
  Whenever one connection layer of a context becomes dirty, all of them become dirty. Other input contexts also become dirty in their connection layers.
  UPDATE: no need; static connection layer + dynamic connection layer that has explicit context inputs
- Renaming is very hard to cache. So the low-level macro cache function can receive (from the high level) a renaming key.
  This renaming key changes the current (sub-)context against which the renamed context is evaluated.
  Normally, every renaming triggers a mid-level-to-low-level translation, so there should be only renaming key.
  UPDATE: don't cache this. Cache code cell hash + input hashes + transformer/reactor/macro declaration dict
- If you .set() a cell and then connect to it (making it non-authoritative), a warning is printed.
  Use .set_default() to avoid this warning.
- There will be a runtime API to control the low-level from the mid-level. This is just another kind of caching; the low-level could as well be regenerated.
  The runtime API can be done automatically, if all mid-level-to-low-level core macros defines cell-to-cell correspondences. These core macros understand all mid-level nodes. It will "just work" for embedded low-level macro nodes too.
  Authoritative cells can be set directly from the mid-level. Setting non-authoritative cells will generate the usual warning. Setting cells that control (low-level) macros will re-execute them (with proper caching).
  UPDATE: better to have the mid-level contain explicit pointers to low-level authoritative data. This way, modifying the low level
    auto-modifies the mid level.  
- There will be an option to sync cells to a file. This must be done in macro mode.
  The sync can be one-way or two-way (only for authoritative cells). When a cell is updated from a file, it is as if it was done using .set()
  A context can be synced to a directory.
  Cell/context symlinks will become Unix file/directory symlinks.
  When a cell/context is destroyed, the file is cleaned up. This can be prevented by a low-level-macro-caching hit.

###

Seamless will consist of three parts:
- A high-level Silk API
- A mid-level execution graph format (SLGraph?)
- A low-level direct API (core)
Only the mid-level will have a formal data format. The other two are informal
(for now) APIs tied to the Python language (for now).
The low-level is as it is now, but with important simplifications:
- The context may only ever grow. Explicit removal of cells/constructs/subcontexts
  is not supported. Only low-level macro re-execution will replace a subcontext.
  All low-level macros will be cached, and always generate a context.
- No more registrars/injection (goes to the mid-level)
- There will be cells and signals, but otherwise, no cell types whatsoever. UPDATE: cells will differ in the supported transport protocols
  Any type checking will be via Silk schemas attached to cells. Detailed schemas
  are more to validate transformer output, since authoritative inputs should have
  already been validated at the high level.
  If there is no schema, cells may contain raw Python objects (discouraged), and
  cannot be serialized. UPDATE: slightly less radical: there is still text,json,cson,python cells
- Symlinks still needed.
- status() will go. Instead, context will have a hook registration API that can be configured to link registration
  names to particular context children. UPDATE: it remains here for now, something to do for 0.3 or so
- Essentially zero runtime support. Small API is essentially for construction time (inside macros). .checksum() stays because its implementation is cell-dependent.
  Beyond that, cells are to be manipulated via managers.
- Managers are more decentralized: one manager per context.
Mid-level:
- Knows about context hierarchy, data cells (with types), code cells (with language),
  transformers (with language and execution semantics), reactors (same), code injection
  (with language). Code injection + hierarchy replaces registrars. Data must be "injected"
  via the normal pin mechanism.
- Also knows about operators such as add, mult, etc.  
- Does not know about high-level macros
- No observers (to high-level). But a hook definition language to define correspondences,
  between high-level and mid-level. Hooks can be informative (mid-level simply can report
  status and value) OR may trigger the re-computation of the entire execution graph
  (if the cell is an input of a high-level macro)
  UPDATE: no need for this, since mid-level is only manipulated from high-level. Results of computations do not confer authority!
- There will be a special library contexts of low-level macros that recognize mid-level graph constructs
  and return low-level contexts. UPDATE: just macros should do
  These contexts are expected to accept connections straightforwardly, and to have hook registration configured.
  The "big low-level macro" (only invoked by the top context) reads in a mid-level graph + such a library,
  and returns a big low-level context (mid-to-low-level translation).
High-level:
Everything is a Silk structure: cells, contexts, transformers, reactors, observers, macros.
But they will be heavily-modified subclasses of Silk. (maybe less modification in the future)
Lots of hooks in the vein "what happens when something assigns to me"
Normally, ctx.a = 2 will create a cell, but it could create a constant too.
"ctx.c = ctx.a + ctx.b" will normally create ctx.c as an operator_add object.
This object will be stored in the data dict.
A Silk context has a single "big high-level macro" to generate a mid-level graph.
(UPDATE: or simply manipulate the graph directly using high-level API...)
This is done by the top-level context (may invoke subcontexts recursively)
It is done again and again whenever a new cell/context/... is added or removed.
(Not when the value is changed, though, unless there is a high-level macro connected to it
  UPDATE: not even then. A high-level macro is nothing but a macro that returns a mid-level graph structure.
  The default language is the Python-Seamless high-level API, but it can be any language)

Serialization
Each level is serialized on its own.
On the high-level, the topology is stored, but only the value of authoritative cells.
Mid-level is usually not serialized at all, since generating it is fast.
Low-level by default does not store anything, but cell values (not topology) can be cached
either as hashes or as full values.
Libraries requested by a macro will be included into the serialization (this can be configured to contain
only the name + hash, to save space; requires the library to be present when the serialization is loaded)
UPDATE: for individual cells, this is a feature of LibCell. LibModule topology still to be considered.
Symlinks defined at the interactive level cause only the symlinked item to be included.
UPDATE: have to think about serializing mid-level and/or high-level

Workflow of code development
Standard is to put the code in a context, make one or more unit tests, and to configure the context
that only the code is copied or linked when assigned to.
Todo: some smart tool (based on pyshell) that can launch unit tests in a kernel,
tie a IPython instance to the kernel, and tie a editing window to the kernel for tab completion
(eventually, with breakpoints too).

*******************************************

Low-level macro caching
=======================
When a low-level macro is re-evaluated, it would be a terrible waste of computation to just build and re-execute everything.
Therefore, low-level macro caching will re-use the existing macro result as much as possible.
This builds upon a similar mechanism in seamless 0.1.
- The first thing to do is to put all managers in a halting state. This freezes all worker updates, so copying (substitution) is safe. Sub-macros still get executed.
- For the existing context, a graph is built. The graph of a context consists of a *dependency dict* of input/edit pins,
  the graphs of its children, and the connections. The graph of a worker or macro consists of just the dependency dict (and a type string).
  A dependency of an authoritative cell is the md5sum of its value.
  A dependency of a non-authoritative cell is the dependency graph of the worker that generated it.
  Cells may have only one input, this is strictly enforced.
  UPDATE: just of the direct children may be enough.... until you reach authoritative cells
- Then, the macro is (re-)executed as normal, but again, with all managers in a halting state. For the generated context, a graph is built. Each cell and worker
  in the generated context is checked against the current context, and substituted if possible. (clean = substitution, dirty = no substitution).
  substitution rules are as follows:
  - Workers and cells with different dependency dicts (compared to the cache) are dirty
  - Authoritative cells with the same md5sum are clean
  - Workers and cells where all dependencies are clean, are clean
  - Workers and cells that are part of any kind of cycle are dirty (UPDATE: there can't be cycles now)
  - Cache cells and evaluation cells may be dirty, yet the workers that depend on them are clean (except workers not in equilibrium, see below, and whatever depends on them)
  - Otherwise, workers and cells with any dirty dependency, are dirty
- A special rule applies to workers that are not in equilibrium.
    (This includes workers that depend on non-empty event streams)
    They must be "hyper-clean": evaluation cells and ephemeral cells are now also taken into account
    If they are hyper-clean, their kernel is substituted with the kernel from the current context (which is performing the computation)
    Else, they are dirty.
- Reactors that are clean receive a special mark, because whenever they receive an update, the "start" code must be executed, not the "update" code. UPDATE: this is not true, it will be the "update" code.
- Dirty workers are marked with their last previous output and the hashes of their last previous inputs. This gives still a chance for a caching hit if the hashes match.
  These marks persist for the next low-level caching
  Otherwise, the marks are deleted whenever all inputs have been defined.

NOTE: Caching takes place at the time that the outermost macro has been completed.
To make this work, it is imperative that at that time, all sub-macros have been completed, as well.
This is fixed by the fact that macros execute synchronously,
 as soon as their inputs are present.
There are two cases that cannot be fixed in this manner:
- Macros with an exported inputpin whose input goes above the outermost macro that is being re-run.
  Future solution: right before cache evaluarion, look at all macro inputpins, and (pre-)set their value if their input is external.
- Macros that depend on worker output.
  Future solution: allow the worker to be marked, and do a
  special equilibrate() using these workers right before cache evaluation.


## Some thoughts on high-level syntax
Assigning an attribute to a value creates a new Silk cell with that value.
Assigning an attribute to an existing (sub)cell does no longer trigger a rename,
but creates a new cell of the same type, that is alias-connected. Cells must be
explicitly renamed.
Assigning an attribute to a context works as before (leading to a rename) but
you can configure the context as copy-upon-assignment, which means that it gets
deep-copied instead.
Pin export/forwarding will work as usual.
It is possible to seal a context in macro mode, disallowing the creation of new
attributes.
No more cell-like or worker-like contexts. However, it is possible to override
assignment, so that ctx.a = thiscontext (rename)
becomes ctx.a = thiscontext.thistransformer.output (capturing the result).
Contexts will have a new API dict, containing two sub-dicts, "method" and "property".
This is to allow contexts to behave more like Python class instances.
Each sub-dict must contain cells that are children of the context.
(the manager knows API relationships, so renaming these cells,
  or their parent contexts, will be checked!)
Example:
ctx.v = cell("int").set(5)
ctx.code_a = cell("text").set("return ctx.v.value * 10")
ctx.api.property["a"] = ctx.code_a
print(ctx.a) #50
ctx.code_a = cell("text").set("lambda ctx, factor: return ctx.v.value * factor")
ctx.api.method["b"] = ctx.code_b
print(ctx.b(2)) #10
API dicts get stored upon serialization as cell paths.
The method dict may contain any special method (__xxx__).
Context's __getattribute__ sets a flag whenever a special method gets invoked.
As long as the flag is set (i.e. until the end of the API code cell execution),
special methods on ctx are no longer looked up first in the API method dict.
## UPDATE
Also do symlinks: context child that has name A but points to name B. Essential for slash0 transformers!

- There must be a lot of API/proxy magic on top of the assign operator.
For example, ctx.a = ctx.b.state_shared would create a state-shared connection,
ctx.a = ctx.b.message_based would create a message-based connection.  
- Likewise, if ctx.tf is a transformer, then ctx.tf.self.input would be its input
auto cell. You may assign ctx.a = ctx.tf.self.input and then reverse the connection.
By default, this would be state-sharing.
You could the modify the connection so that only the schema is state-shared, but
the value connection is message-based. Then, you would have the following usage
patterns:
- ctx.a.spam = 5 is *example-based programming*. By giving example data, Seamless
  can infer the schema. In addition, it provides a *unit test* for ctx.tf.
- ctx.tf.spam (=> ctx.tf.self.spam) provides a *default value*.
What you do is that you configure ctx so that assignment to ctx is re-written
as assignment to ctx.tf. You configure ctx.tf as copy-upon-assignment. You save
ctx as "tf.seamless". In the main program, you do:
  ctx.mytf = seamless.fromfile("tf.seamless")
Now you have imported a fresh copy of ctx.tf as "mytf". mytf.spam is initally 5,
but you can assign it to any other constant, or to a cell. In both cases, the
default 5 will be overwritten.


## Thoughts on library
You don't import the seamless lib, you add it as a subcontext into your main
context (TODO: support loading subcontexts!!!; also, the .lib
context and its subcontexts must be copy-upon-assignment instead of rename-upon-assignment  ).
!!! lib mounter !!! normally, only read access. libdevel mounter with write access. Robogit (libgit2) to commit changes.
UPDATE: not exactly a "mounter"; core.lib system instead.
UPDATE: Seamless servers serve *high-level* contexts or transformers. They are contacted during translation.
 The context is *marked* by the high-level topology.
 In fact, there must be *two* service topologies (with checksums): a smaller one to *retrieve* the result;
  from this, evaluation and logging parameters (and workers that operate on them) should be stripped.
  And the full one to *compute* the result (which may still be refused, e.g. too many cores are requested).
 During (re-)translation, requests like create and delete can be sent.
 If the response is positive, then the cell checksums and values will be offered by the *low-level*.
 NOTE: the service checksum system must be a bit different from the semantic checksums used in local low-level evaluation.
  The reasons are 1. it is very difficult to compute a checksum for a code cell in an arbitrary programming language,
   unless a parser for that language has been installed; 2. service checksums will be global and therefore must be secure;
   semantic checksums are just to avoid unnecessary re-computation => use SHA3-512 for service checksums
 It is possible that the response is negative for the context-as-a-whole, but positive for sub-contexts and transformers
 Therefore, if there are multiple Seamless servers, they must be assigned a priority.
 Also, there is a spectrum between positive and negative: one server may accept the whole context, or even have the result cached,
  but another may accept only an empty context to which the cells must then be added (less efficient).


## UPDATE of the UPDATE: Towards flexible and cloud-compatible evaluation / Seamless collaborative protocol
Seamless services: Serve a (high-level) context, transformer or reactor; or a low-level transformer or reactor.
Services are substituted during graph translation:
  High level: send the high-level graph over the wire, together with cell updates.
  Low level: after finding a service, don't build a core.transformer, but a service.core.transformer
Local execution is a fallback, but service substitution can be enforced or disabled on an individual basis.
 (Also the kind of allowed services can be configured; services may promise fast execution, or not)
Service discovery happens with an explicit discover() command.
Common characteristic of services is that they synchronize cells.
When Seamless talks to a Seamless server, it offers a cell.
(UPDATE: this is not strictly true. Cell-cell connections between a serviced context
  and the outside world are indeed treated as state shared. However pin connections are exposed too!)
First, it provides the checksum. The server will then respond with one of the following responses ("transfer negotiation"):
 0. Server context is dead; client must re-initialize the server context and and re-send all cells.
    However, the context ID always stays the same.
 1. Cell checksum is already known and cached, no need to transfer
 2. Mounter is known; no need to transfer; server will retrieve cell value from mounter by itself
    UPDATE: seems like YAGNI
 3. Please transfer cell value
 4. The transfer of this cell or cell value is forbidden
 5. Reverse update request: the server asks the client to update one or more cells.
    This is most common in case of an interactive fix of the code (so the code cell has now a different checksum)
 6. Redirect (to another website). Maybe make this rare?
 7. Challenge. This server refuses secret cells. You must prove that you have the actual cell value.
 Server configuration involves primarily these responses.
 Other configuration is what kind of evaluation/resource-claiming meta-parameters to accept, and what kind of logging is returned.

 Type of servers:
 ### VERY NEW (Nov 2018) UPDATE: See "Seamless shared authority" below.
 0. will be ripped, and B. will be a special case of A.
 REST API and web sockets will be organized. 
 OLD:
 0. Dynamic HTML using websockets. Completely unrelated. UPDATE: ...and ripped
 A. Two-way synchronization (collaborative protocol). Uses websocket/crossbar server, pub/sub
    NOTE: text cells should support a git backend to resolve simultaneous edits on different sections of the text.
 B-D. One-way synchronization. Client manipulates cells, assuming that no other client does.
 B. Remote context server. Service is remote context server. It starts empty context (in Docker image)
    Returns a context ID / URL. The URL might be somewhere else.
    URL provides REST API:
    1. equilibrate
    2. set <cell name>
    3. read <cell name>
    4. create <cell name, worker, subcontext, etc.>
    5. delete <cell name, worker, subcontext, etc.>    
 C. Interactive service. As in B, but:
    - The server starts a full context, not an empty one.
    - 4. and 5. are forbidden
    - 2. is regulated. Some cells may not be set at all; for others, only certain values (or maximum sizes) may be acceptable.
    - 3. may be regulated as well
 D. Atomic service.
    1. Standard Seamless client. Negotiates cell transfer as in C.
     No concept of context ID.
     Returns a request URL: in a request, all cells are submitted, then
      the context is equilibrated, then the result is returned.
     Service configuration (internal):
     - Starts full context in Docker image (as in C)
     - One cell of the context must be marked as "result" cell, some others as input cells
     - Some cells may be marked as slow-changing. Contexts are kept alive, and when a request has the same values
       for the slow-changing cells, it is sent to the same context instance.
       This is just an implementation detail; it is assumed that this has no influence on context state.
   2. Web service. Non-Seamless client (Python, JavaScript, ...).
       As 1., but request URL is called directly.
       No transfer negotiation request, needs extra configuration to regulate this.
   3. Web server. As 2., but over CGI. Web form needs to (auto-)generated.
  Instead of Docker images, the service may also run on bare metal. It may even run in-process (dummy server).
  For atomic services, a HPC backend may be used as well (e.g. Slurm jobs).

Note that service *names* do not play any role. For logging purposes, one could be provided, otherwise it is just the local context name.

The idea is that the RPBS will host a global Seamless server (Cloudless) that accepts any context registration, and will
 be a *router* for services.
A server A, B, C, D1, D2, D3 and an HTML page for D3 are in principle auto-generated upon context registration, but customization is possible. For example, a cell may be designated as D3 HTML cell. Multiple D1 with multiple slow-change configs are possible.
After some time, context instances will be killed off, this can also be configured.
The RPBS server will have authorization: authorized registrations will have access to more resources.

How services are found:
At startup, Seamless server(s) and mounters are read from the environmental variables.
In the Seamless client, for any context, if a service is not found, Seamless reverts to local evaluation.
However, a context may be marked as "must be service".
A context may also be marked already with a context ID. The context ID is a huge (64 bit) global number that monotonically
 increases; the RPBS server guarantees that two interactive requests made under the same context ID will always modify the
 same context (as long as it is alive), no matter if they come from the same client or not.

Jupyter:
Jupyter is only useful for interactive servers and services (A-C). Seamless-in-a-notebook is an interactive client that
 can also in-line visualize HTML.
The RPBS server can offer interactive services as a "watermarked notebook". A notebook template is registered, and when a
 new context instance is created, the notebook is returned with the context ID filled in.
These notebooks can run everywhere: it can be downloaded and run locally, or at the RPBS. In the latter case,
 some "privileged connections" to the services can be set up in the form of mounters.
In the same vein, the RPBS will allow you to clone the entire RPBS server into a private sandbox copy,
and the URI will be similarly watermarked into the notebook. You can then override any service you like, without affecting
 other users.
Maybe every context submitted to an RPBS server should go into a robogit (libgit2) repo. Pull requests from sandbox server
 repos are then possible. (People should create their own Github account, then push the robogit@RPBS to there.
  RPBS should provide an in-Docker command line shell for this kind of thing)

Docker repo:
- Let apt/pip/conda/yum dump their state; define a Docker image as this state, on top of base Docker images
- The base images has all repo locations set to RPBS mirrors; for Ubuntu, PyPI, etc., all specific to a date and never changing
  This way we can guarantee version control and support indefinitely

Dependency server: Takes a dependency URN and gives some JSON as a result, preferably
with human-readable documentation and some kind of package name + version + checksum
in the format of apt/yum/pypi/conda.
Will be hosted at the RPBS.

Further thoughts on checksums
=============================
hash/checksum are SHA3-512:
  This uniquely defines what a cell or computation *is* (like Magnet URIs).
  Checksums of JSON structures containing checksums can be computed (aka Merkle trees)

global ID: an 128-bit unsigned integer that signifies a session ID
  (for interactive service instances) or a job ID (for non-interactive ones).
  The ID is guaranteed to be globally unique.
  The RPBS will maintain an ID server that returns the last ID + 1.

In general, a computation is defined by the following:
1. The type (context, transformer, reactor or macro)
   and the seamless version (more precisely, the version of the mid-level syntax)
2. A topology (mid-level declaration of contexts, cells, workers and connections)
   This includes the cell types, and the language of code cells, but no cell values
   NOTE: this is mid-level; the high-level must mark a context with its topology before
    it can be considered to be sent to a service.
   If type is "context": when marking, the topology cells are classified as:
   a. non-authoritative
   b. authoritative, but not connected to the outside
   c. authoritative, and connected to the outside.
   The server may impose restrictions, e.g. say that only category c. cells may be defined by the client,
    or refuse because a particular cell cannot be in category c. (for example, cells it considers private).
   *Any worker or context that has external connections that involve blocks/allocators is ineligible for service*
3. The value of authoritative cells, including the schemas.
  Checksums of those values will always be computed on the raw/text data (see above)
  The "grand cell value" includes the cell type (part of the topology).
4. Broader topology, that includes cells and workers that only define Report cells
   and Logging cells
5. Broader values:
  - Values of non-authoritative cells
  - Values of transformer equilibrium state
  - Values of evaluation parameters and resource claims
6. The environment. This includes:
  - Dependencies of the code (see dependency server above)
  - Docker version? Linux drivers?

I. Seamless "universal computation" dogma: a computation is defined by 1-3 only. A "grand checksum"
 of a computation is a single hash that uniquely defines 1-3.
4. and 5. are derivative data, they may be submitted, or added by the server.
II. Seamless "durable environment" dogma
When it comes to environments, every computation has only valid and invalid environments.
Valid environments give the (unique) correct result, whereas incorrect environments result in an error.
This means that a dependency library must never have the same code result in two different
 non-error results. The results must either be the same between two versions, or
 one version must give an error. If the library does not guarantee this, the code must do version checking.
NOTE: there is a "base environment" that escapes this notion. The "base environment" includes
- Docker version
- Interpreter versions (Python, node.js)
- Compiler versions (GCC, CUDA)
- Relevant drivers and hardware (GPU, CPU instruction set), insofar exposed to the docker image
Memory does conform to the notion, though, as does time-constrained execution.

When submitting, 1-3 is to check if the computation has been done. If not, 1-6 are submitted.
Submitting 4-6 (in full or in part) is optional: a server may infer it automatically.
A server may also refuse service because of values in 4-6.

Checksum/ID/cell servers
All of these servers are hosted at the RPBS, but they may forget entries after some time.
Seamless can be configured with a list of these servers that can be queried.

Computation hash-server:
hash1 => hash2. hash1 is the grand checksum of a computation, hash2 is its result.

Reverse computation hash-server:
Same as above, but hash2 => hash1. Note that hash2 must be rather long for this to work,
 as there are several computations that can give the same result.

Computation server:
hash => computation. hash1 is the grand checksum of a computation JSON,
  computation is the computation JSON itself.
  Only non-error computations (status OK) are cached thus.

NOTE: make computation servers also for low-level transformers, and for reactors
 marked as "pure".

Cell server:
hash+hash2 => value. Serves grand cell values (can be rather big). hash is the
hash of the cell value, whereas hash2 is the hash of the cell type (part of the topology).

Location server:
hash => (URI, mode). The hash is from a cell value.
Mode can be None.
If mode is "substitute", URI is a template into which the hash must be substituted, e.g. if URI is a cell server.

Description server:
hash => description. To give a semantic text description for a hash/

Context ID server:
ID => JSON, for context IDs. Returns an URI to a live interactive service instance.
  JSON has the format of   <protocol>: (URI, flag)
  protocol: dynamic HTML (websocket), two-way synchronization (websocket), one-way synchronization (REST)
  This URI must be unique for the ID. If the URI is dead, the instance will have died.
  Mode can be None.
  If mode is "substitute", URI is a template into which the hash must be substituted, e.g. if URI is a cell server.
  If mode is "submit", then the ID itself must be GETted/posted to the URI (together with any other data)
  RPBS server will accept only one registration per ID

Job ID server:
ID => JSON, for job IDs. Returns an URI to a job result of an atomic service.
  RPBS server will accept only one registration per ID.
  JSON has the format of   <protocol>: (URI, mode)
  protocol: one-way synchronization (REST), direct web service (REST), CGI server
  If mode is "substitute", URI is a template into which the hash must be substituted, e.g. if URI is a cell server.
  If mode is "submit", then the ID itself must be GETted/posted to the URI (together with any other data)
  RPBS server will accept only one registration per ID

Obsoletion server:
hash1+hash2 => hash3. Indicates that hash1 is now obsolete and should be replaced by hash3.
Reasons for obsoletion are: a new version, a bugfix, etc.
hash2 indicates the cell type.
hash1 must be rather long/specific for this to work.

Equivalence server:
hash1+hash2 => hash3. Same as obsoletion server, but indicates that hash3+hash2
is semantically equivalent to hash1+hash2.
This is typically because of adding comments, whitespace or reordering to a
source code, text or CSON file (normally not JSON, though)

Anathema server:
hash1 => hash2. hash1 is the grand checksum of a computation, hash2 is that of its result.
hash2 is anathema if it is fundamentally wrong, due to:
- Bugs in seamless
- Bugs in the library environment
- Bugs in Docker / kernel drivers
- Violation in the code of Seamless purity (cells with such code can also be stored in an "impurity server" as hash+hash2)
- Violation of the Seamless dependency dogma (e.g. logging cells connected to non-logging output cells)
  (such computations can also be stored in a "dogma violation server")
A Seamless server may consult the anathema server before returning its result.
If the underlying value of hash2 is sufficiently long, it may be stored in a separate "bogus server".

Finally: "marking".
Obsoletion server, reverse computation server, equivalence server, impurity server and bogus server require hashes of high-complexity values as an input. Otherwise, they are not an unique result.
Therefore, it is possible to make them accept one extra optional argument.
When registering a hash, a *random* 512-bit mark may be generated, and this may be used to mark even low-complexity
 cells (e.g. an integer cell with value "4", or an empty text cell).
Seamless will store the mark in the high-level context, and submit it to the service every time.

"Durability"
Environment dependencies may have different levels of durability (the Seamless durability dogma).
0. Zero durability. Results will be different, even with the same arguments.
   Example: Gromacs/AMBER and anything else that runs on the GPU
1. Low (exact version) durability. Results will be the same only with the exact same version.
   Example: ATTRACT, HADDOCK.
2. High (minor version) durability.
   Code is durable between two versions X and Y, that have the same major version,
     but where Y is later than X.
   2a. Code that runs under X will either give the same result as under Y, or give an exception    
   2a+. Code that runs under X will either give the same result under Y (forward compatibility guaranteed)
   2b. Code that runs under Y will either give the same result under X, or give an exception.
   compatibility 2 means 2a & 2b. compatibility 2+ means 2a+ and 2b+.
   Examples: Python? (2+?)
3. Complete (major version) durability. The same, but Y and X do not need to have the same major version
   (or there is only one major version)
   Examples: POSIX tools?

RPBS will host a durability server.
For non-durable (incomplete durability) environment dependencies:
  Seamless versions will include a list of default dependency versions (for 1. and 2.) or minimum versions (for 2a. and 3a.)
  The + is just convenient for servers.
A durability overestimation of a computation is a special kind of bogus, it should be marked as such.
A zero-durability computation may still be stored, because the result is "as good as any".
When we start scientific reproducibility test servers, zero-durability computations must be repeated, together
 with computations that require a random seed (just change the seed). And of course, all computations must be either
 local or from trusted service servers, not from the scientists themselves.

UPDATE: for durability 1+, make a "requirement repo" that can automatically convert a list
 of requirement (e.g. a list of Python modules) to a list of version-stamped packages (pip, nix, apt). RPBS will a) be a mirror and b) snapshot package versions every month. Example: capability "numpy" + Nov 27 2018 => pip package numpy-1.15.4 (the state of PyPI on Nov 01 2018, i.e. "RPBS-Linux 18.11")
 Different capabilities can be combined and made into a Docker image using docker2repo/binder.

##/UPDATE of UPDATE
(after this, text may be outdated)

## UPDATE: Towards flexible and cloud-compatible evaluation
All (low-level) transformers and reactors will have a hidden JSON input pin "(sl_)evaluation".
For (low-level) macros, the presence or absence of "evaluation" is meta-parameter.
"evaluation" contains evaluation strategies. These are irrelevant to the *outcome* of the computation:
 the same result will be obtained no matter the evaluation strategy.
Seamless understands this, and merely a change in evaluation will not trigger a recompute.
The most obvious parameters are "synchronous"/"asynchronous", "process/thread", and the shared
state of Numpy arrays (binary data) and of plain-form data.
Less obvious ones: number of processors, force local (non-service) evaluation, force service evaluation
There will be a global fallback "evaluation" dict as well.
# UPDATE:
Don't follow exactly this scheme. Pins will now have simple evaluation parameters in their arguments.
Low-level macro caching will know that they don't matter.
In addition, a new cell type "evaluation cell" will be treated likewise.
This is just for the purpose of dependency tracking, though, not cache substitution (see above).
Evaluation cells may contain more complex evaluation parameters.
Their semantic meaning is at the high level, no low-level support or core mid-level support.


The seamless collaborative protocol (high level)
================================================

### UPDATE: completely outdated. See "Seamless shared authority" below.
The collaborative protocol is a means to share *cells*, like dynamic_html, but then bidirectionally
The idea is that a cell is bound to a unique "cell channel", so that two programs or web browsers can pub/sub to the channel
At the core, there is a single Seamless router (Crossbar instance) at the RPBS.
Websocketserver is gone: seamless looks for the router when it is initialized, or launches a "pocket router".
Every seamless kernel has its own ID, every context has its own ID, and every cell has its own ID. This triple of IDs forms the channel ID.
Seamless IDs are read from os.environ, else it is 0.
Seamless can expose its cell (for read or read/write) by registering itself as a channel with the Seamless router.
This opens an WAMP channels "seamless-host-{channelID}", "seamless-guest-{channelID}" and an RPC "seamless-state-{channelID}".
The seamless instance who registered the channel becomes the *host*, other clients can become *guests*
A guest can subscribe as follows:
- It subscribes to the *host* channel. Messages over the host channel are marked with a number N
- The guest invokes the state RPC, receiving back the state, and a number M, indicating the number of messages that were used to generate the state
- The guest can now  listen to messages. If the message N is not equal to M+1, the guest has to re-request the state (so packet loss is in principle possible!)  
- If read/write, the guest can now also publish to the *guest* channel. Only the host is subscribed to the guest channel.
The host sends every state change (both endogenous and those coming from the guest channel) over the host channel, and marks them with a number N. Guest channel messages are not numbered.
UPDATE: this replaces the Websocketserver, but not the parallel REST API.
UPDATE: It should be possible to send an (U)RI, instead of the cell value, over the network.
 The host and guest need to negotate in advance:
 - which protocols (HTTP, database, etc.) are accepted for URIs
 - which domains are acceptable. Both may have access to the same database, but not necessarily.
   (This is somewhat related to having this database as a mount backend, but not exactly)


Seamless shared authority
=========================

There are two concepts of shared authority: *context* authority and *cell* authority.
*context* authority regulates where a context graph is being computed. The *worker*
 performs the computation, whereas the *master* controls it. For each seamless instance,
 a context for which the seamless instance is the master but not the worker is a 
 *delegated context*.
For *cell* authority, the *host* owns and holds the data, whereas a *client* may request
or modify the data.
1. Context authority 
 The context consists of a context graph, the in-context cell values, the connections,
  and the values of the incoming connections. 
 Context authority can be interactive or non-interactive. 
 Non-interactive computing can be dumb or smart.
 For non-interactive computing, the mechanism is as follows:
  The master has any number of non-interactive workers, in the form of REST servers.
  Whenever the context is updated, a new *context request* is built. 
  A. In "dumb" mode, this request contains the entire context, including values. 
  This request is sent to a worker.
  Any previous context request is canceled. It is up to the worker to re-use pieces
  of earlier context requests (e.g preliminary results).  
  B. In "smart" mode, the master also acts as host of the cell values and connection values.
  It registers itself as host, providing identifiers for each cell and connection (see below).
  The context request all values are then replaced by the sharing handle (see below). 
  The worker may then act as client, requesting cell/connection values on demand. 
  The master may also ask: what about this graph? and get back some information on how easy
   it would be to execute.
  For any context request in any mode, the worker must either refuse quickly, return an error, or return the result (as either a value or as a sharing handle). 
The master has any number of interactive workers, in the form of REST servers.
The master may send the following requests, which a worker must quickly either acknowledge or refuse:
  - How busy are you? (Do you have free channels? A graph topology may be sent already)
  - Open a new channel (returns a channel ID; a graph topology may be sent already)
  On an opened channel:
  - (re)define graph topology (may include some values; flag can be defined to keep "internal cells")
  - Set cell/connection value
  - Get cell/connection value
  - Are you in equilibrium?
  - Shut down the channel (the worker is free to ignore this)
  In addition, the master may send "equilibrate", which may take a long time to answer.
  Every request is marked with an ascending ID, and the worker response is marked with the same ID.
  All values are sent as sharing handles. The master must register itself as host for them.
2. Cell authority
Cell authority can be local or remote. Local means that the state of the cell is maintained by the
 current seamless context. If it is remote, the state is maintained by a host elsewhere.
All cells can be set *by value* or *by checksum*. 
Setting by value always computes the checksum. Setting by checksum does nothing if the checksum stays the same.
Every cell that is not in a delegated context can be directly queried for its value.
(internal cells of delegated contexts may be queried from interactive workers, if the flag is set ).
Direct query of local cells gives the following result:
A. cell is None: return None
B. value mode: return value.
C. checksum mode: see below. 
3. Cell sharing
Local cells may be shared, which means that the current Seamless instance is their host.
(remote cells may also be shared, in which the Seamless instance is simply a router for that cell).
Cell sharing involves three operations:
3a. Publishing changes on the "cell share channel". Every Seamless instance may have exactly one
 channel, implemented as a websocket server. Upon connecting to the channel, a client will receive a share list (of shared cell names and types) and their checksums, and the global host marker. Whenever the host changes a shared cell, the change gets published on the cell share channel, and the host marker increases by one.
 Share lists may be registered under a "namespace". Clients indicate their preferred namespace
 in the path url (e.g, http://localhost/seamless/mynamespace:1234 for a cell share channel served on
 http://localhost/seamless:1234)
 The change is published as a share handle, of the format (cell name, checksum, host marker).
 Upon receiving the share handle, the client is expected to store it, together with the
  name of the host, if the client has more than one host.
 The other event that is being published is when the share list is being re-defined.
 (The high level should do this after re-translation, if there was no change)
 Internally, the host maintains for each shared cell what was the host marker that changed it
  most recently.
3b. Querying the "host channel". Every host has one, implementing five REST methods:
  - query value. The argument is a cell name. The host channel will return the cell value
    (including storage, form and/or schema, if applicable), the checksum, and the current host marker.
  - query update. The argument is a share handle. If the checksum is different than the stored one
    AND the host marker is later, return as above. Else, just return the current checksum + host marker. 
    If the host marker is earlier, then some routing has gone at different speed. In that case, the
     client should keep querying the update until the (routed) host catches up. Routing must always
     preserve the upstream host ID!
  - cancel all queries.
  - query set value (see 3c.)
  - set value (see 3c.)
  NOTE: at the high level, only one top-level context can expose shares for each namespace. 
  During context translation, for that namespace, both the cell share channel and the host channel should delay any response until the translation is done.
3c. Sending values to the host channel. 
A "query set value" can be done with just a shared handle. The host may send four possible responses:
- accept; please call "set value"
- reject; host marker is too old (i.e., the value has been updated in the meantime)
  The client will receive the current host marker in the response, and can use this to force the issue.
- success; submitted checksum found in cache (new host marker is returned)
- fail; cell is no longer shared.
Then, the value itself can be submitted with "set value", which returns the new host marker,
 or an error.

Querying checksum mode:
First, search local cache. If successful, return value.
Else, send a simultaneous request to all registered network cache servers. In addition, if the cell is remote, send a "query update" request to the host.
As soon as any network cache successfully yields a significant portion (depending on the value size) of the value, cancel all other cache requests. As soon as the full value has been obtained, if the cell is remote, cancel the host "query update" request, and return the value.
On the other hand, as soon as "query update" request starts yielding a value, cancel all network cache requests. When complete, return value.
If the cell is not remote, and network caching fails, report an error.
If "query update" returns the same handle, wait for the network cache. If it fails, query the host
with "query value".
If "query update" indicates a routing delay, run "query update" until solved, then run "query value".

After any cell (local or remote) in checksum mode has been successfully queried/retrieved from cache, it enters value mode. But Seamless is free to put any cell back in checksum mode, adding its value to local cache.
Local cache must not discard a value as long as any cell in checksum mode holds on to it, although it may offload to network cache (under the same constraints).


NOTE: transformer authority is a special case of context authority. It has the same modes
(interactive, non-interactive smart, and non-interactive dumb).
Transformer authority and cell authority are maintained at the low level. Context authority
 at the high level.
NOTE: There can be only one interactive and one non-interactive worker, but cluster managers
 can function as one virtual worker. They can deal with all kinds of meta-parameters, and do
 smart dispatch based on the contents of the graphs and values.




