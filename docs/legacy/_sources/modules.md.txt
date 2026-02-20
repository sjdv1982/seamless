# Modules

The purpose of modules is to represent extra code objects that are added to a transformation.

If added to a Python transformation, a Seamless module of Python (or IPython) code becomes a Python module or package, whereas a Seamless module of compiled code becomes a shared library.

Modules added to non-Python transformations are currently not supported.

***IMPORTANT: This documentation section is a stub.***

**Relevant test examples:**

- [module-simplified.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/module-simplified.py)

See [Running tests](https://sjdv1982.github.io/seamless/sphinx/html/getting-started.html#running-tests-locally) on how to execute tests.

<!-- (Builds upon transformers) ... pin celltype "module"! -->

## Python modules

***IMPORTANT: This documentation section is a stub.***

**Relevant test examples:**

- [module.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/module.py)

- [multi-module.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/multi-module.py)

## IPython modules

***IMPORTANT: This documentation section is a stub.***

**Relevant test examples:**

- [cython_.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/library.py)

## Compiled modules

***IMPORTANT: This documentation section is an early draft. The raw text material is shown below***

Modules written in a compiled language are currently only only implemented at the low level. High-level access via the Module class is to be implemented. However, every compiled transformer contains a main_module object, that can be modified via the Transformer class... also, you could construct a compiled module yourself as a structured cell and insert it using pin celltype "module" (see module-simplified.py) ...

<!-- (Builds upon compiled transformers) -->