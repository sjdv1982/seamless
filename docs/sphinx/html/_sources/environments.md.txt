# Environments

The goal of environments is to describe a software environment with certain tools or packages installed, where 1) specific transformer code can run; 2) additional programming languages are understood and can be executed.

For 1), environments are defined for a specific transformer, and revolve around conda, command line tools and/or Docker images.
Transformer environments are part of the transformation, and passed along to any job slave or job manager. Currently, Seamless transformer environments are a bit informal and do not necessarily define a guaranteed reproducible environment. This is hopefully improved in future versions.

For 2), environments are defined for the context as a whole, and revolve around defining languages, compilers, and IPython bridges.

***IMPORTANT: This documentation section is a stub.***

## Transformer environments

***IMPORTANT: This documentation section is a stub.***

## Context environments

***IMPORTANT: This documentation section is a stub.***

## Relevant test examples

- [environment.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/environment.py)

- [environment2.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/environment2.py)

- [environment3.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/environment3.py)

- [environment4.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/environment4.py)

- [environment5.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/environment5.py)

- [environment6.py](https://github.com/sjdv1982/seamless/tree/stable/tests/highlevel/environment6.py)

See [Running tests](https://sjdv1982.github.io/seamless/sphinx/html/getting-started.html#running-tests-locally) on how to execute tests.


<!--
D3. Environment

Intro:

- Conda, powers, which, image, Docker

-->