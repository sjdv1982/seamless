# seamless_transformer.transformer_class

Wrap a function in a Seamless transformer.

## `seamless_transformer.transformer_class.ArgsWrapper`

- kind: `class`
- signature: `ArgsWrapper`

Wrapper around an imperative transformer's celltypes.

## `seamless_transformer.transformer_class.CelltypesWrapper`

- kind: `class`
- signature: `CelltypesWrapper`

Wrapper around an imperative transformer's celltypes.

## `seamless_transformer.transformer_class.DirectTransformer`

- kind: `class`
- signature: `DirectTransformer`

Transformer that can be called and gives an immediate result

## `seamless_transformer.transformer_class.GlobalsWrapper`

- kind: `class`
- signature: `GlobalsWrapper`

Wrapper around an imperative transformer's global namespace.

## `seamless_transformer.transformer_class.ModulesWrapper`

- kind: `class`
- signature: `ModulesWrapper`

Wrapper around an imperative transformer's imported modules.

## `seamless_transformer.transformer_class.Transformer`

- kind: `class`
- signature: `Transformer`

Transformer.
Transformers can be called as normal functions, but
the source code of the function and the arguments are converted
into a Seamless Transformation that is returned.

## `seamless_transformer.transformer_class.Transformer.allow_input_fingertip`

- kind: `method`
- signature: `allow_input_fingertip(self, value)`

_No docstring._

## `seamless_transformer.transformer_class.Transformer.args`

- kind: `method`
- signature: `args(self)`

The arguments

## `seamless_transformer.transformer_class.Transformer.celltypes`

- kind: `method`
- signature: `celltypes(self)`

The celltypes

## `seamless_transformer.transformer_class.Transformer.code`

- kind: `method`
- signature: `code(self, code)`

_No docstring._

## `seamless_transformer.transformer_class.Transformer.direct_print`

- kind: `method`
- signature: `direct_print(self, value)`

_No docstring._

## `seamless_transformer.transformer_class.Transformer.driver`

- kind: `method`
- signature: `driver(self, value)`

_No docstring._

## `seamless_transformer.transformer_class.Transformer.globals`

- kind: `method`
- signature: `globals(self)`

Global symbols injected via modules.main.

## `seamless_transformer.transformer_class.Transformer.language`

- kind: `method`
- signature: `language(self, lang)`

_No docstring._

## `seamless_transformer.transformer_class.Transformer.local`

- kind: `method`
- signature: `local(self, value)`

_No docstring._

## `seamless_transformer.transformer_class.Transformer.meta`

- kind: `method`
- signature: `meta(self, meta)`

_No docstring._

## `seamless_transformer.transformer_class.Transformer.modules`

- kind: `method`
- signature: `modules(self)`

The imported modules

## `seamless_transformer.transformer_class.Transformer.scratch`

- kind: `method`
- signature: `scratch(self, value)`

_No docstring._

## `seamless_transformer.transformer_class.delayed`

- kind: `function`
- signature: `delayed(func, language)`

Return a Transformation object that can be executed later.

## `seamless_transformer.transformer_class.direct`

- kind: `function`
- signature: `direct(func, language)`

Execute immediately, returning the result value.
