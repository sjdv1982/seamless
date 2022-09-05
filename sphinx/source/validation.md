# Validation

**Relevant examples:**

- [basic example](https://github.com/sjdv1982/seamless/tree/stable/examples)

See [Running examples](https://sjdv1982.github.io/seamless/sphinx/html/getting-started.html#running-examples-locally) on how to run examples.

**Relevant test examples:**

- [simplest.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/simplest.py)

- [simpler.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/simpler.py)

As a rule, *validation* happens on the data. Transformation code is not the correct place to do validation.

Validation in Seamless is defined in schema cells. Schema cells contain a superset of JSON Schema. You can write them directly, but it is easier to fill them up using the `Cell.example` attribute. See [this example](https://github.com/sjdv1982/seamless/blob/stable/tests/highlevel/highlink-cpp.py), to be opened with `seamless-ipython -i`.

Validation errors show up in the monitoring. At this point, the monitoring (which had previously its own UX cells) should be adapted so that error messages and progress are displayed in the main web UI.

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
