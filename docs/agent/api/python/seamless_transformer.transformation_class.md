# seamless_transformer.transformation_class

Transformation class

## `seamless_transformer.transformation_class.Transformation`

- kind: `class`
- signature: `Transformation`

Resolve and evaluate transformation checksums, sync or async.

Lifecycle:
- .construct() / await .construction():
    Evaluate dependencies and builds the transformation dict
- .compute() / await .computation() :
    Run the transformation dict and return the result checksum.
- .run() /  await .task() :
    compute, then resolve the result checksum into a value.

## `seamless_transformer.transformation_class.Transformation.allow_input_fingertip`

- kind: `method`
- signature: `allow_input_fingertip(self)`

If True, inputs may be fingertipped when resolving their buffers.

## `seamless_transformer.transformation_class.Transformation.buffer`

- kind: `method`
- signature: `buffer(self)`

_No docstring._

## `seamless_transformer.transformation_class.Transformation.celltype`

- kind: `method`
- signature: `celltype(self)`

_No docstring._

## `seamless_transformer.transformation_class.Transformation.clear_exception`

- kind: `method`
- signature: `clear_exception(self)`

_No docstring._

## `seamless_transformer.transformation_class.Transformation.computation`

- kind: `method`
- signature: `computation(self, require_value)`

Run the transformation and return the checksum.

First, constructs the transformation; then, evaluate its result.
Returns the result checksum
In case of failure, set .exception and return None.

If require_value is True, it is made sure that the value will be available too.
(If only the checksum is available, the transformation will be recomputed.)

## `seamless_transformer.transformation_class.Transformation.compute`

- kind: `method`
- signature: `compute(self)`

Run the transformation and return the checksum.

First, constructs the transformation; then, evaluate its result.
Returns the result checksum
In case of failure, set .exception and return None.

It is made sure that the result checksum is fingertippable (resolvable or recomputable).

## `seamless_transformer.transformation_class.Transformation.construct`

- kind: `method`
- signature: `construct(self)`

Evaluate dependencies and calculate the transformation checksum from the inputs
In case of failure, set .exception and return None

## `seamless_transformer.transformation_class.Transformation.construction`

- kind: `method`
- signature: `construction(self)`

Evaluate dependencies and calculate the transformation checksum from the inputs
In case of failure, set .exception and return None

## `seamless_transformer.transformation_class.Transformation.exception`

- kind: `method`
- signature: `exception(self)`

_No docstring._

## `seamless_transformer.transformation_class.Transformation.logs`

- kind: `method`
- signature: `logs(self)`

_No docstring._

## `seamless_transformer.transformation_class.Transformation.meta`

- kind: `method`
- signature: `meta(self, meta)`

_No docstring._

## `seamless_transformer.transformation_class.Transformation.result_checksum`

- kind: `method`
- signature: `result_checksum(self)`

_No docstring._

## `seamless_transformer.transformation_class.Transformation.run`

- kind: `method`
- signature: `run(self)`

Run the transformation and returns the result,

First runs .compute, then fingertip the result checksum into a value.
Raise RuntimeError in case of an exception.

## `seamless_transformer.transformation_class.Transformation.scratch`

- kind: `method`
- signature: `scratch(self, value)`

_No docstring._

## `seamless_transformer.transformation_class.Transformation.start`

- kind: `method`
- signature: `start(self, *, loop)`

Ensure the computation task is scheduled; return self for chaining.

## `seamless_transformer.transformation_class.Transformation.status`

- kind: `method`
- signature: `status(self)`

_No docstring._

## `seamless_transformer.transformation_class.Transformation.task`

- kind: `method`
- signature: `task(self)`

Create a Task Run the transformation and returns the result,

First runs .compute, then resolve the result checksum into a value.
Raise RuntimeError in case of an exception.

## `seamless_transformer.transformation_class.Transformation.transformation_checksum`

- kind: `method`
- signature: `transformation_checksum(self)`

_No docstring._

## `seamless_transformer.transformation_class.Transformation.value`

- kind: `method`
- signature: `value(self)`

_No docstring._

## `seamless_transformer.transformation_class.TransformationError`

- kind: `class`
- signature: `TransformationError`

_No docstring._

## `seamless_transformer.transformation_class._compute_executor_max_workers`

- kind: `function`
- signature: `_compute_executor_max_workers()`

_No docstring._

## `seamless_transformer.transformation_class._dask_available`

- kind: `function`
- signature: `_dask_available()`

_No docstring._

## `seamless_transformer.transformation_class._ensure_loop_running`

- kind: `function`
- signature: `_ensure_loop_running(loop)`

Run the given event loop in a background thread if it is not already running.

## `seamless_transformer.transformation_class._format_exception`

- kind: `function`
- signature: `_format_exception(exc)`

_No docstring._

## `seamless_transformer.transformation_class.compute_transformation_sync`

- kind: `function`
- signature: `compute_transformation_sync(transformation, *, require_value)`

_No docstring._

## `seamless_transformer.transformation_class.loop_is_nested`

- kind: `function`
- signature: `loop_is_nested(loop)`

_No docstring._

## `seamless_transformer.transformation_class.running_in_jupyter`

- kind: `function`
- signature: `running_in_jupyter()`

Function to detect Jupyter-like environments:

- That have default running event loop. This prevents
sync evaluation because that blocks on coroutines running in the same loop

- That support top-level await as a go-to alternative

## `seamless_transformer.transformation_class.transformation_from_dict`

- kind: `function`
- signature: `transformation_from_dict(transformation_dict, *, meta, scratch, tf_dunder)`

Build a Transformation from an already-prepared transformation dict.

## `seamless_transformer.transformation_class.transformation_from_pretransformation`

- kind: `function`
- signature: `transformation_from_pretransformation(pre_transformation, *, upstream_dependencies, meta, scratch, tf_dunder)`

Build a Transformation from a PreTransformation
