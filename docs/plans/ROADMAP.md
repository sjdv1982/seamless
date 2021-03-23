UPDATE Dec 2020
===============
see KNOWN-GLITCHES.txt
Get rid of special syntax << and >>
   => getattr shouldn't give proxies

UPDATE Nov 2020
===============
Current state:
- Much more stable execution
- Deep cells are now there
- Map-reduce stdlib is on the way
- Cloudless has a working prototype

For the next version:
- Split off .mixed and .silk code into seamless-silk project. DONE
  Build a pypi package for it.
  Make it one of the dependencies of cloudless.
  Adapt cloudless to use it for encoding.
  => bash/docker transformers can produce multiple files that are non text

- Jobless: concept of eagerness (first-resort, last-resort backend)
  Make a jobless last-resort backend based on run-transformation. If needed, fire up database adapter on the fly.


- bash/docker transformers no longer need tar. Instead, RESULT can be a directory.

- Shell into each Python / bash transformer. Docker image for bash transformers supported.
Rip/subsume "debug" mode. Compiled transformer keeps debug mode, and has no shell.

- At the high level, rip [getattr(Context) => Proxy].
- At the high-level, allow descriptions/docstrings everywhere (Cell, Transformer, but also pin, subcell).
  Continue with ergonomics and user docs.

- Inside a transformer, input pins should be "mixed" by default, not silk.
As it is, the pins are already called "mixed", but a schema is attached if
it can be retrieved from the input schema, else an empty schema (core/transformation.py)
Make a special pin celltype "silk" that has the current behavior

- Notebook integration: an IPython magic that execs code in a "ctx-mapped namespace",
  so that "a[:10]" becomes "ctx.a.value.unsilk[:10]"
  Cache ctx.a.value . Setting ctx values is not possible (ctx itself is not mapped)
  Also make a version that doesn't unsilk.

- Autoconnect method for Transformer.
  Connect all pins to parent context cells of the same name.
  Example:
  def add(a, b):
    return a+b
  ctx.sub.tf = add
  ctx.sub.tf.autoconnect()
  => try to connect ctx.sub.a and ctx.sub.b, if they exist

- Better highlevel API tooling. Especially:
  - Rename a cell/transformer/context/...
  - Copy a cell/transformer/context/... .
    This is particularly useful for transformers, as copy() reuses topology and schema,
    i.e. does something akin to CWL's CommandLineTool instantiation.

Set up a network infrastructure at console
==========================================
UPDATE Feb 2020: initial protocol for cloudless is ready!
Need to implement seamless-tools.txt,
 and draw inspiration from docs/archive/seamless-services.txt / checksums.txt
  TODO: Need to implement snooping (over web socket).
graphID maps to:
  - template ctx.seamless + delta checksum dict,
    PLUS:
  - template status.seamless + delta checksum dict
  Templates are registered under service name (which also can import their .zip into Redis). Only admins can update templates (to update a service, or to update current graphs)
Internally, cloudless keeps graphID-to-Docker container mapping;
  - ports 5813, 5138 are mapped to ephemeral ports
  - Docker container is killed if there is no traffic for too long
  - Docker container is killed and re-launched if the graphID has its template changed. This should change index.html into something that asks for a refresh every few seconds (snooping connection should say this!)
  - new Docker container is launched if graphID receives traffic again
  - Docker containers are thin, all work is done in jobslave containers,
    communicate over communionserver
Finally, take features from usability-todo.txt, and think of how to regulate:
- Docker image execution (esp Docker transformers)
- Policy of whitelisting/forwarding certain transformer code checksums
- Authorization: use cookies with limited validity, bound to an IP address.
 OAuth is too complicated, ORCID isn't nice. Basic HTTP authentication has no expiry support.
For graphIDs created by anonymous users:
  - Create an anonymous long-lived cookie for seamless.rpbs.paris-univ-diderot.fr/graph/...
  - A website (e.g seamless.rpbs.paris-univ-diderot.fr/sesam/graphID=XYZ&cookie=...) will set the cookie,
    and redirect to seamless.rpbs.paris-univ-diderot.fr/graph/XYZ
For other graphIDs, the user cookie (after login) can also be the authorization. The user can disable or revoke
 anonymous cookies.
An authorization failure, by default, renders a screen where the user can ask a *new* graphID with the *same*
delta checksum dict. For the user, this feels as a read-only (to be more precise, a copy-on-write) view on the graph.
Docker containers could be launched as an ipykernel (e.g. using jupyter console) so that an admin can connect
 to it (notebooks cannot connect to an existing kernel, unfortunately; perhaps they could be launched from
 a notebook to begin with?). On the other hand, the graph data could simple be loaded by the admin in any context.

DaReUS-Loop/PepCyclizer example
===============================
  - Banks!
  - Not command-line based, i.e. don't use SnakeMake, use BCSearch routines
  - Need high-level Macro structure: needs deep structure, and automatic transformer
    map/reduce has now been ripped.
  - PyPPP docker image: code is open source, but SVM model is secret
