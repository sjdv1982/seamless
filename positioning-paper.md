# Semantic Scope, Semantic Strength, and Portable Scientific Facts

Consider two programs. One downloads the latest weather observations, combines them with a forecast model, produces a map, uploads the result, and sends a notification if severe weather is detected. The other calculates the first billion digits of \(\pi\).

Both are computations, but they make very different demands on a framework that attempts to reason about them. The weather program interacts continuously with an external world. “Run the same computation again” is already an ambiguous instruction: the latest observations have changed, remote services may have changed, and some of its actions deliberately alter external state. A framework such as Airflow is quite comfortable with this. It can coordinate downloads, database queries, scripts, web services, retries and notifications without requiring the whole process to behave as a deterministic function.

The calculation of \(\pi\) lies near the other extreme. Its inputs and algorithm can, in principle, determine its result completely. If it is run twice and produces different digits, something has gone wrong. Here much stronger questions become meaningful. Is this exactly the same computation as one performed earlier? Which changes to its code or dependencies would make it a different computation? Is a result obtained elsewhere still valid? If somebody has already calculated the required digits, can they be reused without repeating the computation?

Between these extremes lies a large range of scientific and technical computation. A molecular-dynamics simulation may be deterministic given suitable code, parameters and starting state, yet depend on a complex software environment. A genomics pipeline may consist of command-line programs connected by files. A Python analysis may pass nested arrays and JSON-like values between scripts. Compiled programs may communicate through typed binary interfaces and shared libraries. These are all deterministic computations in a useful sense, but frameworks differ greatly in how much of their structure they can see and reason about.

This motivates two separate concepts.

**Semantic scope** is the class of computational objects and activities to which a framework's own semantic model applies.

**Semantic strength** is the set of sound conclusions that the framework can draw about computations within that scope: in particular about dependency, computational identity, validity, equivalence and reuse.

The distinction matters because scope and strength pull in different directions. Airflow has an exceptionally broad semantic scope: almost anything that can be expressed as an operation or task can participate in an Airflow workflow. But Airflow deliberately assumes little about what those tasks mean, and therefore has relatively weak semantics for computational identity and validity.

Frameworks such as Bazel, Nix and Unison make the opposite trade. They restrict the objects over which they reason, but obtain much stronger semantics inside those boundaries. Bazel reasons about declared actions and artifacts; Nix about derivations and their recursively identified inputs; Unison about Unison code and values.

It is only after making this distinction that it becomes useful to ask which framework is more *universal*. Universality is then not the trivial ability to execute arbitrary code. It is the more demanding ability to extend semantic scope while retaining semantic strength.

## The superscope of deterministic computation

For the remainder of the comparison, it is useful to set aside intrinsically stateful or effectful activities such as sending an email, charging a credit card, waiting for human approval, or querying “the current weather.” They remain important computations in the operational sense, but the notions of identity and reuse that concern us become much weaker.

Instead, consider the **superscope of deterministic computation**: computations for which an identifiable set of determinants is assumed to establish an identifiable result.

Within this superscope, reuse is potentially much stronger than “this task ran successfully before.” If the determinants of a computation are known, a framework may be able to decide that a previous result remains valid without executing the computation again.

This is where the important differences between workflow systems, build systems, package systems and content-addressed programming models emerge.

## The filesystem and Unix scope

The first major semantic scope is the **filesystem or Unix scope**. Its computational objects are files, directories, commands and processes. A program consumes some files and produces others.

Unix makes this an extraordinarily successful composition boundary. A program does not have to understand the implementation language, internal data structures or execution strategy of the program that produced its input. It merely receives a file. This permits heterogeneous tools to be assembled into large computational workflows.

The classic Make algorithm contains a remarkably effective trick for reasoning about validity in this scope. Suppose an output file is produced from several input files by a recipe. If the output already exists and is newer than all of its prerequisites, the system may treat the result as reusable. If an input or relevant recipe dependency is newer than the output, the recipe must be run again.

In simplified form:

\[
\max\bigl(t(\text{inputs}),t(\text{recipe dependencies})\bigr)
<
t(\text{output})
\]

suggests that the existing output remains valid.

The system has not proved that the computation would produce the same bytes. It does not need to. Filesystem modification times act as a cheap approximation to causal history.

This idea underlies an extraordinarily successful family of systems. Snakemake, Nextflow and related scientific workflow frameworks considerably enrich the model with explicit rules, parameters, software environments, provenance information and more sophisticated invalidation criteria, but the underlying semantic universe remains recognizably Unix-like:

\[
\text{artifacts} + \text{processes} \rightarrow \text{artifacts}.
\]

Within this universe, remarkably strong automation is possible.

Bazel occupies roughly the same semantic scope but uses a substantially stronger validity criterion. Rather than relying primarily on the temporal relation between prerequisites and outputs, an action can be identified from declared inputs, command, execution properties and other determinants. Matching action identity can justify reuse even when the result is available only in a remote cache.

Thus Make-like freshness checking, scientific workflow invalidation and Bazel action caching should not be regarded as fundamentally different scopes. They represent different semantic strengths over approximately the same filesystem/process model.

The limitation of that scope is equally important. A file is opaque. If two JSON files contain the same logical value but differ in whitespace or key order, they are different byte objects. If one element changes inside a terabyte-sized data structure, the artifact as a whole has changed. The framework normally does not know what semantic part changed or whether the difference matters downstream.

The filesystem is therefore both an extremely successful composition mechanism and a semantic boundary.

## Structured values and script-glued computation

A second scope appears when the framework sees through the file container and deals directly with **structured values**.

This is the natural world of script-glued computation. Python scripts, command-line tools, web services and independently developed programs exchange strings, numbers, lists, dictionaries, arrays and records.

JSON is the obvious gravitational center of this scope. This is not because JSON is uniquely expressive, but because it provides a widely shared value model independent of any particular programming language.

At this level, identity can become more semantic. The serializations

```text
{"a": 1, "b": 2}
```

and

```text
{"b":2,"a":1}
```

may denote the same structured value. With a canonical representation, the checksum can identify that value rather than a particular incidental spelling of it.

The transition is important. At filesystem scope, the object is a byte sequence. At structured-value scope, the byte sequence is one possible representation of an object.

This permits stronger reuse while retaining heterogeneous implementation. Producer and consumer do not need to share a language or runtime; they need only agree on the identity and representation of the exchanged value.

Much scientific computing naturally falls into this region. Numerical arrays, parameter dictionaries, tables, molecular structures and nested records are richer computational objects than files, yet need not belong to one programming language.

## Typed components and linker-glued computation

A third scope lies deeper inside the program boundary: **typed-component or linker-glued computation**.

Here the relevant objects are separately constructed computational components connected through explicit interfaces. Shared libraries, object files, exported symbols, RPC schemas and binary protocols inhabit this world.

The gravitational center is no longer merely JSON-like values, but typed and schema-defined representations: Protocol Buffers are one example, alongside language ABIs, interface definitions and other binary contracts.

Again, the significant step is the movement of the semantic boundary.

At filesystem scope, a shared library is a file.

At component scope, it can instead be considered as a collection of definitions exposed through typed interfaces.

This opens the possibility of more precise dependency reasoning. A change somewhere inside a large library need not necessarily imply a semantically relevant change to every consumer. In principle, identity could follow the definitions and data that actually participate.

Conventional build systems generally remain more conservative. If a low-level library changes, dependent artifacts are commonly rebuilt even when the changed implementation detail has no effect on them. This is safe, but it exposes the difference between detecting a changed cause and establishing a changed result.

## Total semantic unification

The fourth scope eliminates most of these boundaries entirely.

In a system such as Unison, code, values, types and dependencies inhabit a common content-addressed semantic universe. A function is not fundamentally a source file identified by pathname. Its identity follows structurally from its definition and the identities of the definitions on which it depends.

Dependency reasoning can therefore penetrate much further into program structure than when the fundamental objects are files and process invocations.

The attraction is clear. Distinctions that external orchestration systems must reconstruct—source versus artifact, code versus value, symbolic name versus dependency identity—largely become internal properties of one semantic system.

The cost is equally clear: this semantic strength is obtained inside the Unison universe.

The four scopes therefore suggest a useful progression:

**filesystem artifacts → structured values → typed components → unified code and data.**

They are not strict mathematical subsets. Rather, they describe how far into a deterministic computation a framework's identity and validity semantics penetrate before reaching an opaque boundary.

## Semantic strength: what licenses reuse?

Within any of these scopes, semantic strength becomes most concrete when deciding whether previously obtained work can be reused.

Different frameworks employ different **reuse predicates**: conditions under which an existing result is accepted in place of executing a computation again.

The classic filesystem predicate is temporal. If the inputs and recipe have apparently not changed since the output was created, accept the output.

A content-based workflow can use a stronger predicate: if the identified input contents, parameters and recipe have not changed, accept the previous output.

Bazel strengthens this into action identity. If the action and all determinants represented by its action key are identical, an existing result associated with that action may be reused.

Nix uses recursively defined recipe provenance. An output belongs to a derivation whose identity follows from the recipe and identified dependency closure.

These predicates are increasingly precise descriptions of *why a result was produced*. But precision of provenance is not the same thing as semantic equivalence of results.

Suppose one comment is changed in a source repository used to build a low-level library. A source checksum changes, causing a new derivation or build action. The resulting library may nevertheless be byte-for-byte identical. If so, two computational histories have **converged**.

This exposes two fundamentally different reuse questions:

> Has an equivalent computation already been performed?

and

> Does the required result already exist?

Recipe- or action-keyed systems primarily answer the first question. Content identity can also answer the second.

Neither is universally superior. Action identity can permit reuse without executing the action at all; convergence can only be discovered once identical content has somehow been produced or independently identified. But once convergence is established, provenance need no longer determine the identity of the result.

This distinction becomes increasingly important in scientific computation. The same dataset may be produced by different software implementations, by different environments, or by independent research groups. If the result has a content identity of its own, these paths can converge onto the same object.

A strong reuse model therefore benefits from keeping two identities distinct:

\[
\text{identity of the computation}
\]

and

\[
\text{identity of the result}.
\]

Purity and referential transparency make the relation between them tractable, but they remain supporting properties. The central issue is what equivalences the framework can recognize and therefore what reuse it can justify.

## Three attitudes toward the environment

The execution environment reveals another fundamental distinction.

Bazel takes a predominantly **hermetic or contractual** approach. Relevant properties of the environment belong among the determinants of an action. A changed compiler, toolchain or environmental dependency can therefore establish a different action identity.

This is excellent engineering. Potential hidden causes are brought inside the validity boundary, making cache reuse conservative and predictable.

Unison takes a different, almost **mathematical** approach. Because code, types and values inhabit a controlled semantic universe, the execution environment is largely intended not to participate in the meaning of a pure computation. Correct implementations realize the semantics of the language.

A third position is possible: a **scientific or Popperian** treatment of deterministic computation. This is one of the design choices made by Seamless.

Here, a deterministic transformation expresses a falsifiable claim:

\[
T \rightarrow R.
\]

The execution environment is not necessarily absorbed into the identity of \(T\). Instead, different compatible environments can provide independent tests of the same claim:

\[
(T,E_1)\rightarrow R
\]

\[
(T,E_2)\rightarrow R'.
\]

If \(R'=R\), the deterministic claim survives this replication.

If \(R'\neq R\), the assumption that the environmental difference was irrelevant has been falsified.

This is a deliberately scientific view of reproducibility. Reproducing a calculation by exactly recreating its original environment is valuable, but reproducing the same identified transformation under a distinct compatible environment provides a different and, in an important sense, stronger test.

The three approaches therefore make different epistemic choices.

**Bazel controls the environment.**

**Unison abstracts the environment away through semantic control.**

**Seamless exposes environmental independence to empirical test.**

This is also the point at which Seamless enters the comparison naturally. Until now the taxonomy applies independently of it. The Popperian environment model is not merely another point on an existing scale; it is a distinct design choice about what computational identity means.

## First-class checksums and remote identity

A second distinctive choice appears when computation crosses machine boundaries.

In many systems, hashes are internal mechanisms used to implement caches. A user names an action, derivation or artifact; internally, the system calculates hashes that help locate previous results.

Seamless instead makes checksums **first-class computational objects**.

This changes the semantics of distribution.

Suppose a computation depends on a large value \(X\), identified by checksum \(H(X)\). Knowing \(H(X)\) is enough to establish the identity of the dependency even if the bytes of \(X\) are not locally present.

Thus several notions can be separated:

**identity**, **location**, **materialization**, and **persistence**.

A value may be known by identity without being locally materialized.

A transformation may depend on it without triggering immediate transfer.

If execution eventually needs the bytes, they can be obtained by **fingertipping** from an available source.

An intermediate result may be **scratch**: computationally valid and fully identified, yet not promoted merely for that reason into permanent storage.

These are not only storage optimizations. They permit the semantic graph of a computation to exist independently of the current physical arrangement of its data.

A remote checksum is therefore stronger than a pointer to an object in a particular cache. It is an identity that can remain unchanged across storage systems and computational sites.

## Federation and portable scientific facts

Once computational identity is independent of location and materialization, distribution can become **federation**.

A local cache says:

> I have already computed this.

A shared build cache says:

> Someone using this computational system has already computed this.

Federated content identity can support a stronger statement:

> This result already exists.

That difference is important for science.

A computational result should ideally retain its identity when it crosses machine, project, storage-system and institutional boundaries. Such a result can be regarded as a **portable scientific fact**.

A pathname cannot serve this role. `/home/alice/results/model.dat` derives its identity from Alice's filesystem.

An action-cache entry is more portable, but remains interpreted through the computational system and action identity that produced it.

A first-class checksum can assert simply that a value with this identity exists.

Another researcher can use that identity directly as the input to further computation. They may materialize the value only if necessary. They may obtain it from another repository. They may recompute it independently.

If independent computation yields the same content identity, distinct computational histories converge onto the same result.

If it yields a different result, the claimed deterministic relation has been challenged.

This connects federation directly to the Popperian treatment of environment. A shared result need not become unquestionable simply because others reuse it. Reuse and replication remain compatible.

Federation can therefore support both central mechanisms of cumulative science:

**standing on the shoulders of giants**, by building directly on previous results;

and **independent replication**, by retaining the ability to test those results again.

For this purpose, Bazel and Unison expose complementary limitations. Bazel's strongest reusable identities remain closely tied to actions and their execution determinants. Unison gives extraordinarily strong identities inside its unified semantic universe, but external objects must cross into that universe rather than simply carrying an independent checksum identity through it.

First-class remote checksums instead make external portability part of the semantic model itself.

## Toward computational universality

Only now does *universality* become a useful description.

Airflow shows how broad semantic scope can become when little is assumed about task meaning. Make, Snakemake, Nextflow and related systems demonstrate the remarkable utility of the Unix artifact/process scope. Bazel shows how much semantic strength can be added within that same broad scope. Nix demonstrates the power of recursively identified provenance. Unison shows how strong identity semantics can become when code and data are unified.

These systems also expose the trade-offs.

Breadth alone is not universality if the framework can say almost nothing about computational identity.

Strength alone is not universality if it is obtained only by retreating into a very narrow semantic universe.

The more interesting objective is to preserve **semantic strength while extending semantic scope**.

Seamless approaches this objective from the superscope of deterministic scientific computation. It does not attempt Airflow's general operational scope, nor does it require Unison-like total semantic unification. Instead, it attempts to retain strong notions of dependency, identity, validity and reuse across heterogeneous deterministic computations.

Two further choices distinguish that attempt.

First, reproducibility is treated scientifically: environmental independence may be tested and falsified rather than being guaranteed solely by incorporating the environment into computational identity.

Second, checksums are first-class and remote. Computational identities can therefore survive independently of location, materialization and institutional ownership.

The eventual goal is consequently stronger than efficient caching or reproducible workflows.

It is an environment in which computational results can become **portable scientific facts**: precisely identified, reusable across computational boundaries, capable of convergent discovery, independently replicable and falsifiable, and suitable as foundations for further computation.
