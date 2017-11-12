# Towards seamless 0.2

Seamless will be divided into high-level and low-level.

# Low-level

Pretty much as it is now, but some things will be ripped.
There will be a new struct primitive (documented below).
There will be a new Silk container primitive (documented below)
Some changes/added features to contexts.

## cell
Data is now stored internally as Python objects, rather than JSON.
Many basic types will disappear. There will be only
one text/string type, no subtypes for HTML, vertex shaders and whatnot.
"pythoncell" will disappear.
There will be only one "mixed" type (the old "json" type). Mixed cells contain
plain or binary data, or a mixture of the two. cell("mixed") may receive a
second construction argument *form*, which is "pure-plain", "pure-binary",
"mixed-plain", "mixed-binary" or a nested dict/list thereof. This aids in
serialization.
No docson, or similar.

## transformer, reactor
Mostly unchanged, but they will no longer be macros: their dictionaries have
to be provided up-front and can never change.
Almost exclusively, low-level transformers/reactors will be created *inside*
high-level macros.
If those macros are cached, then re-creating transformers/reactors is cheap.
Anonymous transformers and reactors are not allowed, they must be explicitly assigned
 to a context.

## context
In principle unchanged, but some added features.
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

## registrars
Will disappear. There will be dedicated Silk cells for registering stuff.
No more registering of Python *objects*: transformer/reactor kernels have to do
 their own code evals.
Seamless core.managers will have a dedicated API for Silk schema registering,
as well as registering Seamless contexts.

## observers
Still there, although probably a bit harder to work with
(they won't work on auto cells, only on low-level cells)

## macros
Low-level macros are simplified. They take at most one argument, a "mixed" cell.
The argument *must* be a cell: taking constants is not supported.
To construct a macro, provide the macro factory with a name, a code string and a dict
with a few options (caching; one or zero arguments; code language).
The macro decorator is a simple wrapper around the macro factory.
However, the resulting macro becomes a direct child of the context
(possibly anonymously) and can be only called as such.
Macros as free-floating Python objects are no longer supported.
Name, code string and option dict are stored in the context. Changing the code string is
not supported, but you can create a new macro under the same name that overwrites the old one.
This means that you don't import the seamless lib, you add it as a subcontext into your main
context (TODO: support loading subcontexts!!!; also, the .lib
context and its subcontexts must be copy-upon-assignment instead of rename-upon-assignment  ).
Macros always create a context. Transformers and reactors are no longer macros.
As before, macros implement reconnection machinery and optional caching.
Registrar macros will be eliminated.

## struct
A struct is a manager (but *not* a container!) for structured data.
Upon construction, a struct cell takes:
- a *struct schema* parameter
- an optional *mode* parameter
- an optional *form* parameter (see mixed cells)
The struct schema is either a basic cell type (scalar struct; including "mixed"),
or a nested list/dict of basic cell (composite struct).
A scalar struct can be connected to and from cells/pins/structs that have the corresponding type.
A composite struct can only be connected to and from cells/pins/structs of type "mixed".
The *mode* parameter is "input", "output" or "edit"
Mode must be "input" to receive connections (from cells, structs or outputpins), or to
receive a link).
Mode must be "output" to send connections (to cells, structs or inputpins), or to send links.
Mode must be "edit" to connect to editpins (or edit structs).
Links: when object X has a link to struct Y, it means that Y does not hold any state, but that
X holds the state for both of them. X may be itself a struct, as long as X itself has a link to
some other object.
X may send Y *update messages*, after Y tells X in
which messages it is interested (because of outgoing connections from its children).
Links can also be bidirectional (Y may send update messages back to X).
Accessing a composite struct may create a child struct, with the same mode as the parent.
If the mode is "output", a link is created from (part of) the parent to the child.
If the mode is "edit", that link is bidirectional.
If the mode is "input", a link is created from the child to (part of) the parent.
The parent will hold a weakref, which is returned on subsequent access.
The weakref will be hardened when the child builds connections, and re-softened
when the child has no more.
A struct must receive exactly one link. The schemas must match.
"input" structs may receive one connection.
Alternatively, "input" structs may receive zero links/connections but have *all* of its children received a link/connection
(or all of their children, etc.)
"output" and "edit" structs may link/connect to any number of structs/cells.
Struct links can be exposed as *link pins*, and exported as such on a context.
It is also possible to force-create a link even with a schema mismatch: this will make
the link invalid and non-functional, but the purpose is to have this fixed later via the macro reconnection
machinery, after one struct or the other has been re-created with a
new (matching) schema. The same is not supported for connections.
Again, *structs do not hold any state*. They merely serve to pass along update messages and
to connect composite objects (Silk objects!) to scalar cells.

## Silk manager

A Silk manager is a wrapper around a Silk object (which itself wraps a Silk schema,
a data instance, and a form dict). There is an API (similar to cell.value)
so that the wrapped Silk object (including the schema) can be directly accessed and manipulated.
From the Silk schema, the Silk manager auto-generates a struct schema
which is updated whenever the Silk schema changes.
The Silk manager does not hold any state by itself.
The data object, the Silk schema, the struct schema and the form dict are available as editpins
and must be connected.
A Silk manager is constructed with an *access dict* (since a Silk manager
isn't a macro, this dict is constant). A Silk manager exposes its data object
via a struct link pin, under the name "struct_self", under the struct schema.
For every key in the parameter dict, an additional struct link pin is provided.
Example:
struct schema: {"a": {"b": {"c": "float"}}}
access dict: {"pin1": "a", "pin2": "a.b", "pin3": "a.b.c"}
Pins:
struct_self, linked to .self, struct schema {"a": {"b": {"c": "float"}}}
struct_pin1, linked to .self.a, struct schema {"b": {"c": "float"}}
struct_pin2, linked to .self.a.b, struct schema {"c": "float"}
struct_pin3, linked to .self.a.b.c, struct schema "float".
Additionally, the Silk manager has a mode "input"/"output"/"edit",
which determines the mode of the struct link pins.

# High-level
All high-level cells are contexts with API dicts, generated via a (low-level)
macro that takes no arguments.

## Proxies
Access wrappers around a Silk manager + access dict, as generated by the 0.2 auto API.
Manipulations are modulated by an *access path*, essentially saying which property,
sub-property etc. is being accessed.
Assignment to a value does the following steps:
- Tentatively, inserts the type of the value into the Silk schema. Rolls back if an exception.
- Tentatively, assigns the value to the Silk object. Rolls back if an exception.
Assignment to an outputpin/editpin/cell/proxy does the following:
- The same as assigning to a value; but if it is a proxy, try to copy the schema outright.
- Modifying the access dict (removing paths that start with this one).
  This creates an additional struct pin on the Silk manager, and potentially
  destroys others (child properties with incoming connections)
- Make the incoming connection
Assignment to a transformer connects from its output
Assignment to a context connects from its exported output
Assignment of an inputpin/cell to a proxy modifies the access dict (inserting a
  path), then makes an outgoing connection.
Assignment of a new context attribute to a proxy creates a new auto-cell,
with a cell-cell connection from the proxy.

## Auto cells
An auto cell is a wrapper around the following cells:
(1) a data instance
(2) a Silk schema
(3) a struct schema
(4) a form dict.
(5) an access dict
Resource API will be forwarded to that of the underlying cells.
A Silk manager is used to manage (1)-(4).
This Silk manager is inside a context under macro control, and is re-built
whenever the access dict changes. By manipulation of the manager and the
access dict, both the value+schema and the reactive connections of the Silk
object are dynamically controlled.
The auto cell uses the 0.2 auto API. The whole cell works like a proxy, and
attribute access generates proxies with path-modified access to Silk manager
and access dict.
- Assignment of a context attribute to a value creates a new auto-cell, and assigns the value to it
- Some convenience magic like __add__ to generate transformers, such that ctx.c = ctx.a + ctx.b
   (ctx.a and ctx.b are auto-(sub)cells; ctx.c will be a transformer)
In macro mode, auto cells can have their schema and access dict "sealed".

## Signal relay auto cells
A special version of auto cells just for Seamless signals (input and output).

## Auto macro
The auto macro builder is a low-level macro (*not* a low-level macro factory!).
The auto macro builder takes the following meta-arguments:
- a cell that describes the macro arguments (may include macro argument schemas)
- an cell that describes macro parameters, notably "cached"
- a cell for the macro code itself
All cells are sealed auto-cells under a rather strict schema.
Once meta-arguments are given to a macro builder, a macro object is created.
The auto macro object is a context that contains:
- Input pins corresponding to the macro arguments
- The original meta-arguments.
- A low-level macro whose (constant) input is (the value of) the meta-arguments
  The low-level macro creates an inner context. This inner context is copy-upon-assignment.
Assignment to the auto macro object means assignment to this inner context (copy).

## The auto transformer
A context with the following children:
- An "inp" auto cell (API-exposed)
- An "outp" auto cell (API-exposed)
- A signal-relay auto cell (API-exposed) that can accept "signal" in/out
  connections.
- A code cell for Python code (schema-sealed)
- The composite "input" struct of:
  - inp's struct schema
  - outp's struct schema
  - the signal dict cell value
- A low-level macro that takes the struct above as parameter
- The inner context generated by the macro.

The inner context contains a low-level transformer.
The inner context has a input struct link that matches inp's struct schema,
and is connected to inp in this manner. Similar for output/outp.
The inner context has a struct link that matches the struct schema of the signal relay,
and is connected to the relay in this manner.
The inner context contains an "output" struct "i" struct-linked to inp,
and an "input" struct "o" struct-linked to outp.
The inner context contains a struct "r" struct-linked to the signal relay.
The macro generates the transformer inputs-output pin dict based on the composite struct.
All direct children of "i" are connected to the transformer input pins.
The transformer output is connected to "o"
The relay is also connected to/from the input signals/output signals.

The auto transformer has an auto-cell-like API that returns "inp" proxies or "outp"
proxies or "could be both" proxies where appropriate. Each property must be part of
inp or outp but not both. The "could be both" proxy is a special class to see if
the proxy is used to assign to (=> inp) or to assign from (=> outp).

## The auto reactor
Works very much like the auto transformer, except that there are three code objects,
the output object is now composite just like the input object, and there is a dict
that indicates which pins are edit pins.

## UPDATE
The text above talks a lot about connections and links.
On a second thought, it is clear that the old 0.1 connections are not flexible enough,
that there needs to be a new connection API that describes how two cells are connected.
Traditional 0.1 inputpins and outputpins accommodate connections that are message-based
(copying values), except Numpy arrays which are state-shared.
0.1 editpins are also message-based, but bidirectional (including for Numpy arrays).
Cells expose a stateful bidirectional pin. Such a pin can accommodate one incoming
connection and multiple outgoing ones.  In principle, all of those connections
could also be state-sharing, as long as the cell gets notified of state changes.
Structs and managers typically expose pins for connections that are message-based.
In the text above, structs and managers also expose what is called "links" up above, which means two
different things:
- "Links" for the rewriting of messages. This describes the link between
an "output" struct and its children.
- "Links" for direct state-sharing.  This describes the link between a manager
and its storage cells, where the storage cells lend their state,
and receive back a notification that the state has been modified.
Note that "input" structs in fact do hold state. They require a single state-sharing
connection, or separate state-sharing connections for each children. They support
outgoing connections that are either state-shared or message-based.
At the high level:
- The original plan was to have all standard ctx methods, such as ".tofile", also in a
  "self" attribute so that they wouldn't become completely shadowed away by attributes.
  This must become the other way around. ctx.a may be shadowed away by some API method,
  whereas ctx.self.a is guaranteed to return the attribute.
- There must also be an API on connections, i.e. to reverse a connection or
to change its sharing.
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
