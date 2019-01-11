compiled cell translation
  Make native support for BinaryModule (module pin, see injection.py),
   = a MixedCell of dict-of-.o (Numpy arrays) + header.
   low-level transformers (and later, reactors) will have native CFFI support
    to build this (plus cffi-generated C code) into .so (make global Seamless cache) for interfacing
    Marshalling is just a special kind of interfacing, where the marshalling
     code is the transformer code (marshalling transformer).
    A high-level C++ - transformer is "nothing but" a marshalling transformer
     where the C++ code has been folded into one particular BinaryModule called "main".
For now, support for C, C++, Fortran
