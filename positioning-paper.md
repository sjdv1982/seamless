# Semantic Scope, Semantic Strength, and Portable Scientific Facts

Consider two programs. One downloads the latest weather observations, combines them with a forecast model, produces a map, uploads the result, and sends a notification if severe weather is detected. The other calculates the first billion digits of \(\pi\).

Both are computations, but they make very different demands on a framework that attempts to reason about them. The weather program interacts continuously with an external world. “Run the same computation again” is already an ambiguous instruction: the latest observations have changed, remote services may have changed, and some of its actions deliberately alter external state. A framework such as Airflow is quite comfortable with this. It can coordinate downloads, database queries, scripts, web services, retries and notifications without requiring the whole process to behave as a deterministic function.

The calculation of \(\pi\) lies near the other extreme. Its inputs and algorithm can, in principle, determine its result completely. If it is run twice and produces different digits, something has gone wrong. Here much stronger questions become meaningful. Is this exactly the same computation as one performed earlier? Which changes to its code or dependencies would make it a different computation? Is a result obtained elsewhere still valid? If somebody has already calculated the required digits, can they be reused without repeating the computation?

Between these extremes lies a large range of scientific and technical computation. A molecular-dynamics simulation may be deterministic given suitable code, parameters and starting state, yet depend on a complex software environment. A genomics pipeline may consist of command-line programs connected by files. A Python analysis may pass nested arrays and JSON-like values between scripts. Compiled programs may communicate through typed binary interfaces and shared libraries. These are all deterministic computations in a useful sense, but frameworks differ greatly in how much of their structure they can see and reason about.

This motivates two separate concepts.

**Semantic scope** is the class of computational objects and activities to which a framework's own semantic model applies.

**Semantic strength** is the set of justified conclusions that the framework can draw about computations within that scope: in particular about dependency, computational identity, validity, equivalence and reuse.

A conclusion may be justified deductively, because it follows from the assumptions built into the framework's design, or empirically, because it has survived independent tests. The second kind will matter when the execution environment is discussed. And because strength is a set of conclusions, frameworks are not ranked on a single scale: two frameworks can each draw conclusions that the other cannot.

In existing frameworks, scope and strength tend to pull in different directions. Airflow has an exceptionally broad semantic scope: almost anything that can be expressed as an operation or task can participate in an Airflow workflow. But Airflow deliberately assumes little about what those tasks mean, and therefore has relatively weak semantics for computational identity and validity.

Frameworks such as Bazel, Nix and Unison make the opposite trade. They restrict the objects over which they reason, but obtain much stronger semantics inside those boundaries. Bazel reasons about declared actions and artifacts; Nix about derivations and their recursively identified inputs; Unison about Unison code and values.

This is a pattern rather than a law. Make and Bazel reason about essentially the same objects with very different strength. The interesting question is whether a design can widen its scope without paying for it in strength.

It is only after making this distinction that it becomes useful to ask which framework is more *universal*. Universality is then not the trivial ability to execute arbitrary code. It is the more demanding ability to extend semantic scope while retaining semantic strength.

## The superdomain of deterministic computation

For the remainder of the comparison, it is useful to set aside intrinsically stateful or effectful activities such as sending an email, charging a credit card, waiting for human approval, or querying “the current weather.” They remain important computations in the operational sense, but the notions of identity and reuse that concern us become much weaker. State can still be given an identity, but only an opaque one: redun, for example, identifies the state of a database by the causal history of the calls applied to it. Such an identity cannot be reduced to concrete values. The identities that concern us here are transparent: a checksum of a buffer or of a value.

Instead, consider the **superdomain of deterministic computation**: computations for which an identifiable set of determinants is assumed to establish an identifiable result.

Within this superdomain, reuse is potentially much stronger than “this task ran successfully before.” If the determinants of a computation are known, a framework may be able to decide that a previous result remains valid without executing the computation again.

This is where the important differences between workflow systems, build systems, package systems and content-addressed programming models emerge.

What defines this superdomain is **referential transparency**: a computation can be replaced by its result, and a result by any computation that yields it. Every framework that reuses work relies on this, whether or not it says so. A computation is described by its **recipe**: its code together with its inputs. Referential transparency is then a relation between two identities that recur throughout this comparison, the identity of a recipe and the identity of a result. Each recipe yields exactly one result, but one result may be yielded by many recipes.

Recipe identity is meant here extensionally.[^1]

The superdomain contains several **domains of computation**, distinguished by the kind of object that passes between computations: files, structured values, typed components, or the definitions of a single unified language. A domain is a region of computation, not a property of a framework. A framework's semantic scope can then be described by which domains it covers, and by how far its identity semantics penetrate within them.

## The filesystem and Unix domain

The first major domain is the **filesystem or Unix domain**. Its computational objects are files, directories, commands and processes. A program consumes some files and produces others.

Unix makes this an extraordinarily successful composition boundary. A program does not have to understand the implementation language, internal data structures or execution strategy of the program that produced its input. It merely receives a file. This permits heterogeneous tools to be assembled into large computational workflows.

The classic Make algorithm contains a remarkably effective trick for reasoning about validity in this domain. Suppose an output file is produced from several input files by a recipe. If the output already exists and is newer than all of its prerequisites, the system may treat the result as reusable. If an input or relevant recipe dependency is newer than the output, the recipe must be run again.

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

Thus Make-like freshness checking, scientific workflow invalidation and Bazel action caching should not be regarded as fundamentally different semantic scopes. They represent different semantic strengths over approximately the same filesystem/process model.

The limitation of that domain is equally important. A file is opaque. If two JSON files contain the same logical value but differ in whitespace or key order, they are different byte objects. If one element changes inside a terabyte-sized data structure, the artifact as a whole has changed. The framework normally does not know what semantic part changed or whether the difference matters downstream.

The filesystem is therefore both an extremely successful composition mechanism and a semantic boundary.

## Structured values and script-glued computation

A second domain appears when the framework sees through the file container and deals directly with **structured values**.

This is the natural world of script-glued computation. Python scripts, command-line tools, web services and independently developed programs exchange strings, numbers, lists, dictionaries, arrays and records.

JSON is the obvious gravitational center of this domain. This is not because JSON is uniquely expressive, but because it provides a widely shared value model independent of any particular programming language.

At this level, identity can become more semantic. The serializations

```text
{"a": 1, "b": 2}
```

and

```text
{"b":2,"a":1}
```

may denote the same structured value. With a canonical representation, the checksum can identify that value rather than a particular incidental spelling of it.

The transition is important. In the Unix domain, the object is a byte sequence. In the structured-value domain, the byte sequence is one possible representation of an object.

This permits stronger reuse while retaining heterogeneous implementation. Producer and consumer do not need to share a language or runtime; they need only agree on the identity and representation of the exchanged value.

Much scientific computing naturally falls into this region. Numerical arrays, parameter dictionaries, tables, molecular structures and nested records are richer computational objects than files, yet need not belong to one programming language.

## Typed components and linker-glued computation

A third domain lies deeper inside the program boundary: **typed-component or linker-glued computation**.

Here the relevant objects are separately constructed computational components connected through explicit interfaces. Shared libraries, object files, exported symbols, RPC schemas and binary protocols inhabit this world.

The gravitational center is no longer merely JSON-like values, but typed and schema-defined representations: Protocol Buffers are one example, alongside language ABIs, interface definitions and other binary contracts.

Again, the significant step is the movement of the semantic boundary.

In the Unix domain, a shared library is a file.

In the component domain, it can instead be considered as a collection of definitions exposed through typed interfaces.

This opens the possibility of more precise dependency reasoning. A change somewhere inside a large library need not necessarily imply a semantically relevant change to every consumer. In principle, identity could follow the definitions and data that actually participate.

Some toolchains already exploit this: GHC skips recompilation when a module's interface fingerprint is unchanged, and Java builds can compile against interface-only (ABI) jars. Conventional build systems nevertheless remain more conservative in general. If a low-level library changes, dependent artifacts are commonly rebuilt even when the changed implementation detail has no effect on them. This is safe, but it exposes the difference between detecting a changed cause and establishing a changed result.

## Total semantic unification

The fourth domain eliminates most of these boundaries entirely.

In a system such as Unison, code, values, types and dependencies inhabit a common content-addressed semantic universe. A function is not fundamentally a source file identified by pathname. Its identity follows from its syntax, with names removed, and from the identities of everything it refers to.

The attraction is clear. Distinctions that external orchestration systems must reconstruct—source versus artifact, code versus value, symbolic name versus dependency identity—largely become internal properties of one semantic system.

The cost is equally clear: this semantic strength is obtained inside the Unison universe.

The four domains can be ordered by how far identity penetrates before reaching an opaque boundary:

**filesystem artifacts → structured values → typed components → unified code and data.**

This ordering is not a progression that frameworks climb, nor a ranking of semantic scope. Unison penetrates furthest of all, yet has the smallest semantic scope of the frameworks discussed here. Nor are the domains strict mathematical subsets: a framework may cover several at once, and file-based composition remains indispensable however deep the others reach.

## Semantic strength: what licenses reuse?

Within any of these domains, semantic strength becomes most concrete when deciding whether previously obtained work can be reused.

Different frameworks employ different **reuse predicates**: conditions under which an existing result is accepted in place of executing a computation again.

The classic filesystem predicate is temporal. If the inputs and recipe have apparently not changed since the output was created, accept the output.

A content-based workflow can use a stronger predicate: if the identified input contents, parameters and recipe have not changed, accept the previous output.

Bazel strengthens this into action identity. If the action and all determinants represented by its action key are identical, an existing result associated with that action may be reused.

Nix uses recursively defined recipe provenance. An output belongs to a derivation whose identity follows from the recipe and identified dependency closure. Unison identifies code in the same way: its hashes name recipes, not values.

The decisive difference is whether a recipe is identified by the hashes of its input *values*, as in Bazel and content-based workflows, or by the hashes of its input *recipes*, recursively, as in Nix and Unison. Mokhov, Mitchell and Peyton Jones call these constructive and deep constructive traces, and show that the deep kind cannot support early cutoff. Its advantage is that identities are known before execution, so that end products can be fetched without their intermediates. That suits a build system. Scientific computation needs the shallow kind, which also yields a provenance graph, by walking the recorded mappings back from a result. Dhall is the exception that proves the rule: by hashing normal forms it identifies results rather than recipes, but only because it is a total language in which normalization can stand in for evaluation.

Suppose one comment is changed in a source repository used to build a low-level library. A source checksum changes, causing a new derivation or build action. The resulting library may nevertheless be byte-for-byte identical. If so, two computational histories have **converged**.

This exposes two fundamentally different reuse questions:

> Has an equivalent computation already been performed?

and

> Does the required result already exist?

A deep recipe hash can answer only the first question. A shallow one can also answer the second, because each recipe is keyed on the results it consumes: downstream of the converged library, everything is reused.

Bazel's early cutoff is central to its design, but its result identity stays internal to its cache. Nix, Snakemake and redun have added content-addressed modes, but these remain limited or experimental, because they work against an input-addressed core. In none of these systems is result identity first-class: something a computation can take as input, pass on and produce for others.

This distinction becomes increasingly important in scientific computation. The same dataset may be produced by different software implementations, by different environments, or by independent research groups. If the result has a content identity of its own, these paths can converge onto the same object.

A strong reuse model therefore keeps two identities distinct:

\[
\text{identity of the recipe}
\]

and

\[
\text{identity of the result}.
\]

These are the two sides of referential transparency. Caching uses one direction, from recipe to result; recomputation and provenance use the other, from a result to the recipes that yield it. Convergence is the many-to-one structure of the relation. The central issue is what equivalences the framework can recognize and therefore what reuse it can justify.

## Attitudes toward the environment

The execution environment reveals another fundamental distinction.

Reusing a result in an environment where it was never computed is a generalization, and generalizing beyond observed cases is an inductive step: it can be justified, but never guaranteed. Frameworks differ in how they handle that step.

Bazel takes a predominantly **hermetic or contractual** approach. Relevant properties of the environment belong among the determinants of an action. A changed compiler, toolchain or environmental dependency can therefore establish a different action identity.

This is excellent engineering. Potential hidden causes are brought inside the validity boundary, making cache reuse conservative and predictable. In effect, Bazel **refuses the generalization by exclusion**: a result carries no claim about any other environment.

Unison takes a different, almost **mathematical** approach. Because code, types and values inhabit a controlled semantic universe, the execution environment is largely intended not to participate in the meaning of a pure computation. Correct implementations realize the semantics of the language. Unison **refuses the generalization by abstraction**: independence from the environment is guaranteed by the semantics rather than inferred, so there is no real environment left to generalize over.

Make, and by default most workflow systems, take yet another position: they ignore the environment. A cached result is reused wherever it is found. The generalization is made, but never tested. This is **neglect**.

A further position is possible: a **scientific or Popperian** treatment of deterministic computation. This is one of the design choices made by Seamless, and it is the point at which Seamless enters the comparison naturally. Until now the taxonomy applies independently of it.

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

The claim \(T \rightarrow R\) is a claim of referential transparency, and two things can falsify it: the computation may not be deterministic at all, or its result may depend on the environment. Determinism, like independence from the environment, is treated as an assumption about a computation, not a property certified in advance. Even the weather program becomes deterministic once its observations are captured as inputs, and an assumed set of determinants can turn out to be incomplete. Seamless is Popperian about both claims. A transformation found to give different results in the same environment is recorded as irreproducible, which falsifies its determinism; replication across environments tests its independence from the environment.

The cost of each position can be stated in terms of errors. Keying identity on every possible cause is sound but extremely conservative. Changing a comment in a source file, or upgrading the Python interpreter, rarely changes a result checksum, yet both produce a new identity and force a recomputation: a false negative, a valid result that is not reused. The Popperian position accepts the opposite risk, a false positive: reusing a result that would have differed. Replication measures how often this happens, and for most environmental dimensions it is rare. Checksum identity makes the test strict, since legitimate numerical variation, such as a different BLAS or a different order of GPU reductions, also changes a checksum. Such a mismatch falsifies bitwise determinism rather than the scientific result, and it identifies an environmental dimension that matters.

What separates this from neglect is that the generalization stays under test. Seamless records the environment in which a result was obtained, and federation, discussed below, supplies independent replications.

This is a deliberately scientific view of reproducibility. Reproducing a calculation by exactly recreating its original environment is valuable, but reproducing the same identified transformation under a distinct compatible environment provides a different and, in an important sense, stronger test. Projects such as Reproducible Builds and `guix challenge` already compare independently built outputs, but with the environment held fixed. They test hermeticity, not generalization.

The positions amount to a dilemma: generalization across real environments, or soundness, but not both. Bazel and Unison choose soundness, through two different refusals; Bazel pays for it in false negatives. Seamless chooses generalization, and accepts that its conclusions across environments are corroborated rather than proven. Neglect makes the generalization without paying for it.

**Bazel excludes the environment.**

**Unison abstracts the environment away through semantic control.**

**Seamless exposes environmental independence to empirical test.**

The choice is not symmetric. Because Seamless keeps the environment outside the identity of \(T\), results obtained in \(E_1\) and \(E_2\) remain two observations of the same claim, which can be compared. Bazel's conservatism can be enforced inside Seamless as a reuse policy, by discarding cache entries from foreign environments, without changing what a transformation is. The converse fails: removing the environment from Bazel's action key produces neglect rather than testing, because nothing records or compares the outcomes. In terms of strength, Seamless's conclusions about the environment contain Bazel's, and add corroborated generalizations that Bazel's design rules out. Unison's guarantee by semantics cannot be emulated this way; its limitation is one of scope, discussed below.

The Popperian environment model is therefore not merely another point on an existing scale; it is a distinct design choice about what computational identity means.

## First-class checksums and remote identity

A second distinctive choice appears when computation crosses machine boundaries.

In many systems, hashes are internal mechanisms used to implement caches. A user names an action, derivation or artifact; internally, the system calculates hashes that help locate previous results.

Separating identity from location and materialization is not itself new. Nix knows a store path by its identity before the path exists, realizes it by substitution or by building, and can rebuild it after garbage collection. Bazel can build against a remote cache without downloading intermediate outputs. But in these systems the hash remains internal. At the boundary, an external input is still a location plus a hash, such as a URL with a checksum to verify. No computation can take a bare checksum as its input, or produce checksums as results for other computations to consume.

Seamless instead makes checksums **first-class computational objects**. By first-class we mean that a checksum can stand in for the value it identifies: a computation over the checksum has the same identity as the computation over the value, and the value can be obtained from the checksum.

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

First-class status is what keeps location out of identity. If remote storage and remote execution are library functions, they become part of the expressions they wrap. A computation that fetches some of its inputs from remote storage then has a different identity from the same computation over local inputs, and each mixture of local and remote inputs yields yet another: the pathname problem, moved inside the expression. Normalizing such calls away would require the identity function to treat storage as a primitive, at which point it is no longer a library. When checksums are first-class, a computation over checksums has the same identity as the computation over the values they identify, wherever those values are stored.

First-class hashes exist elsewhere, but under restrictions. Unison refers to code only by hash, but by this definition its hashes are not first-class: they name recipes, not values. IPFS and IPLD make content identifiers into values that can be dereferenced, as links inside data, but within a closed data model, discussed below. What is distinctive here is the combination: first-class, remote and open.

## Federation and portable scientific facts

Once computational identity is independent of location and materialization, distribution can become **federation**.

A local cache says:

> I have already computed this.

A shared build cache says:

> Someone using this computational system has already computed this.

Federated content identity can support a stronger statement:

> This transformation yields this result.

That statement does not depend on who computed the result, or where it is stored. And that difference is important for science.

A computational result should ideally retain its identity when it crosses machine, project, storage-system and institutional boundaries. Such a result can be regarded as a **portable scientific fact**.

A pathname cannot serve this role. `/home/alice/results/model.dat` derives its identity from Alice's filesystem.

An action-cache entry is more portable, but remains interpreted through the computational system and action identity that produced it.

A first-class checksum identifies the result independently of any system. The claim that a transformation yields it is what makes it a fact.

Another researcher can use that identity directly as the input to further computation. They may materialize the value only if necessary. They may obtain it from another repository. They may recompute it independently.

If independent computation yields the same content identity, distinct computational histories converge onto the same result.

If it yields a different result, the claimed deterministic relation has been challenged.

This connects federation directly to the Popperian treatment of environment. A shared result need not become unquestionable simply because others reuse it. Reuse and replication remain compatible. Federation also supplies the evidence about false positives: the more computations a federation shares, the better it can tell which environmental dimensions matter, and therefore where generalization is safe.

Across institutions, validity acquires a second meaning. Within one framework, validity usually means freshness: does a previous result still hold after something changed? Between institutions it also means authenticity: was the result really obtained from that transformation? Replication answers this empirically, for the extensional claim. Verifiable computation answers it cryptographically, but only for an intensional notion of identity, which certifies one execution trace rather than any recipe that yields the result.

Federation can therefore support both central mechanisms of cumulative science:

**standing on the shoulders of giants**, by building directly on previous results;

and **independent replication**, by retaining the ability to test those results again.

Both rest on the same substitution. Building on a result replaces a computation by its result; replicating it replaces the result by another computation that should yield it.

For this purpose, Bazel and Unison expose complementary limitations. Bazel's strongest reusable identities remain closely tied to actions and their execution determinants. Unison's hashes name recipes, not values. A computation that refers to an input by hash has a different identity from the same computation with the input written inline; values computed or loaded at run time have no hash that can stand in for them; and a checksum from outside survives only as data that the program must check explicitly. Dhall's normal-form hashes do identify results, but only Dhall expressions have such an identity.

First-class remote checksums instead make external portability part of the semantic model itself. This requires that identity be open to any buffer, which is the subject of the next section.

## Open and closed identity

Every framework in this comparison relates up to three things: **checksums**; **buffers**, the bytes that are hashed; and **values**, what those bytes mean to a computation.

Bazel has checksums and buffers. Its objects are files, and a file's identity is the digest of its bytes. It needs no type system, but it also has no value level, so the structured-value domain is reachable only as opaque files. Unison has checksums and values, but its checksums name recipes, and it has no buffer level of its own: every object is a Unison term. It needs no type system for identity either, and it is closed by construction, since nothing exists for it until it has become a Unison value.

A framework with all three needs a type system to relate buffers and values. The decisive question is then whether that type system is **open** or **closed**: whether every buffer is admissible, with types as interpretations applied on top, or whether a buffer acquires identity only after conversion into the framework's own data model.

IPLD, and the Homestar runtime built on it, is the clearest closed case. Its data model is language-neutral, and its DAG-CBOR codec is canonical in principle: map keys are sorted, and each value has a single encoding. But admission is conditional. Floats are always encoded at 64-bit precision; NaN and the infinities are not part of the data model and must be rejected; there is no array type, so a numerical array becomes opaque bytes plus a convention. The codec is part of the content identifier, so one value has different identities under different codecs, and a large file is chunked into a graph whose identifier depends on import parameters rather than on its bytes alone. Arbitrary JSON or a `.npy` file from outside is not a typed value until it has been converted. Homestar shows that a closed universe need not be tied to one language, since anything that compiles to WebAssembly can participate. It is still closed. Homestar does offer something Seamless does not: checked interface contracts between components, through WebAssembly Interface Types. These concern the safety of composition, not identity or reuse.

A type system can also fail in the other direction. redun identifies Python values by hashing their pickle serialization. This admits almost any Python object, but the identity belongs to Python and depends on the environment: dictionary insertion order changes the bytes, and so can a change in a library's internal module layout, as happened with NumPy 2. Two environments that compute the same value can then report different identities. Replications fail to converge, and apparent falsifications may be artifacts of serialization. The claim that a result holds across environments cannot even be stated. A canonical, language-neutral identity of values is therefore a precondition for Popperian strength.

Seamless's celltype system is open. Every buffer has an identity, the SHA-256 checksum of its bytes, which anyone can verify with standard tools and without Seamless. A celltype is an interpretation of a buffer: as JSON-like plain data, as a binary NumPy array, as a mixture of both, as text or as raw bytes. Arbitrary JSON and arbitrary `.npy` files are valid as they arrive. Conversions between celltypes are classified by their effect on the checksum: trivial conversions and reinterpretations preserve it, while reformatting may change it. Canonical forms are therefore reachable within the model, by reformatting, while the original identity is kept; a closed system obtains canonical form by refusing everything else. Structure is built the same way. A deep cell is a JSON structure that maps strings to checksums. Nested structures arise by building such structures and flattening or filtering them with transformations, which are themselves identified and cached.

Open identity exists elsewhere without a value level: in Bazel's remote content-addressable storage, in Nix's flat fixed-output hashes, in git-annex. Typed value levels exist elsewhere with closed or language-bound identity: IPLD, Unison, redun. We are not aware of another framework that combines open identity with a typed value layer.

This has a consequence for scope. In a closed framework, the depth to which identity penetrates is fixed for everything it admits. In Seamless that depth becomes a property of the interpretation: the same buffer can be treated as an opaque file, as a structured value or as typed binary data without changing its identity. That is how one framework can span the Unix domain, the structured-value domain and typed binary data without closing.

## Toward computational universality

Only now does *universality* become a useful description.

Airflow shows how broad semantic scope can become when little is assumed about task meaning. Make, Snakemake, Nextflow and related systems demonstrate the remarkable utility of the Unix artifact/process domain. Bazel shows how much semantic strength can be added within that same domain. Nix demonstrates the power of recursively identified provenance. Unison shows how deep the identity of recipes can reach when code and data are unified.

These systems also expose the trade-offs.

Breadth alone is not universality if the framework can say almost nothing about computational identity.

Strength alone is not universality if it is obtained only by retreating into a closed semantic universe, whether that universe is one language, as in Unison, or one abstract machine and data model, as in Homestar.

The more interesting objective is to preserve **semantic strength while extending semantic scope**.

Seamless approaches this objective from the superdomain of deterministic scientific computation. It does not attempt Airflow's general operational scope, nor does it require Unison-like total semantic unification. Instead, it attempts to retain strong notions of dependency, identity, validity and reuse across heterogeneous deterministic computations.

Two choices make this possible, and each widens scope and strength at once.

First, identity is open. Any buffer from any source has a checksum identity, and celltypes interpret it without changing it. This admits the Unix and structured-value domains and typed binary data under one identity, which widens scope. It lets the framework recognize the same value across representations, which adds strength. And it allows checksums to be first-class and remote, so that identities survive independently of location, materialization and institutional ownership.

Second, reproducibility is treated scientifically. The environment stays outside the identity of a transformation. This admits native code and real software environments, which widens scope, and it licenses reuse across environments, justified by corroboration and open to falsification, which adds strength.

A closed universe controls both the data it admits and the code it runs. Seamless opens both. This is why the usual pattern, in which scope and strength pull in opposite directions, does not apply to it: the same choices that widen its scope add to its strength. A minimal core helps. Structures such as nested links are expressed as cached transformations over checksum-valued data rather than as new primitives.

The resulting claim can be stated precisely, together with its limits. Counting only conclusions that a framework can reach within its own semantic model, Seamless's strength contains that of the workflow and build systems discussed here, outside three corners defined in advance:

- effectful and stateful computation, the territory of Airflow and of redun's database handles;
- closed semantic universes, such as Unison and Homestar, which obtain their guarantees by controlling what may enter;
- intensional identity, as in verifiable computation, which certifies one execution trace rather than a mapping.

Within the deterministic superdomain, one capability lies outside Seamless's current model: tasks whose result is itself a computation. redun lets a task return an unevaluated expression and caches each such reduction separately, so that a change deep inside a nested workflow does not invalidate the steps that merely route work to it. In Seamless, this would require an expression that evaluates the transformation whose checksum a value contains. Incremental change propagation inside a single computation, as in self-adjusting computation, remains in the corner of closed universes.

Finally, the Popperian choice rests on an empirical premise: much of the scientific software stack, including native code, GPUs, MPI and vendor-tuned numerical libraries, lies outside every abstract machine available today. If deterministic abstract machines come to host that stack, closed universes would absorb much of the territory that the Popperian choice currently serves. The design choice is therefore itself open to falsification.

The eventual goal is consequently stronger than efficient caching or reproducible workflows.

It is an environment in which computational results can become **portable scientific facts**: precisely identified, reusable across computational boundaries, capable of convergent discovery, independently replicable and falsifiable, and suitable as foundations for further computation.

[^1]: That is, what matters is the mapping a computation realizes: any implementation that produces the same result from the same inputs counts as the same computation, however it divides the work and whichever algorithm or compiler it uses. This is the notion that referential transparency presupposes. A stricter, *intensional* notion identifies a computation with one particular execution: one program image running one instruction trace. Verifiable computation, as in zero-knowledge virtual machines, certifies identity in this sense, without trusting whoever performed the execution. That is a stronger guarantee about a single execution, but a narrower notion of identity: a result is certified for one trace, not for any recipe that yields it.
