# Validation

The goal of validation is to make sure that invalid or unreasonable input values do not occur. In Seamless, validation should happen on the *data*, which means *cells* or *transformer input pins*. That means that transformation code can assume that its inputs are sensible, eliminating one class of errors. *Transformation code is not the correct place to do validation*.

The simplest way to do validation is to declare a cell type (see cell documentation). Otherwise, validation happens via *schemas*. Schemas can be only attached to structured cells and to the `Transformer.inp` and `Transformer.result` objects (which are, in fact, structured cells as well). In addition. Seamless schemas have some similarities with Python classes, and can be used for object-oriented programming of cells.

***IMPORTANT: This documentation section is a draft. The preliminary text is shown below***

**Relevant examples:**

- [basic example](https://github.com/sjdv1982/seamless/tree/stable/examples)

See [Running examples](https://sjdv1982.github.io/seamless/sphinx/html/getting-started.html#running-examples-locally) on how to run examples.

**Relevant test examples:**

- [simplest.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/simplest.py)

- [simpler.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/simpler.py)

Validation in Seamless is defined in schema cells. Schema cells contain a superset of JSON Schema. You can write them directly, but it is easier to fill them up using the `Cell.example` attribute. See [this example](https://github.com/sjdv1982/seamless/blob/stable/tests/highlevel/highlink-cpp.py), to be opened with `seamless-ipython -i`.

Schemas are also the place to define APIs to interrogate and manipulate structured cell values, in an object-oriented manner. 
...

Validation errors show up in the monitoring. At this point, the monitoring (which had previously its own UX cells) should be adapted so that error messages and progress are displayed in the main web UI.

...

This is also the time to create tests. A unit test should be a small Seamless context linked to the same files as the main project for code and schema cells. Other tests can be a copy of the main graph with some parameters changed. *Make sure to create some tests that are designed to fail, to verify that a correct and comprehensible error message is reported*.

## Silk

***IMPORTANT: This documentation section is a stub.***

<!--
### D2. Silk

Intro:

- Silk as a wrapper of mixed data; unsilk
- JavaScript-style attribute access
- example (cells and transformers)
- adding validation (cells and transformers)

Intermediate:

- Silk as a handle for structured cells: buffered and auth
- example and JSON schema; linking schemas.
- adding methods
- serialization
- Silk and _SCHEMA pins in transformers
-->
