# seamless

## Exports

This module primarily re-exports public primitives. Export list (`__all__`):

- `Checksum`
- `Buffer`
- `CacheMissError`
- `set_is_worker`
- `is_worker`
- `ensure_open`
- `close`
- `register_close_hook`

For details, see the generated API pages for the underlying implementation modules.

## `seamless.CacheMissError`

- kind: `class`
- signature: `CacheMissError`

Exception for when a checksum cannot be mapped to a buffer

## `seamless.ensure_open`

- kind: `function`
- signature: `ensure_open(op, *, mark_required)`

Raise RuntimeError if Seamless was closed; optionally mark that close is required.

## `seamless.is_worker`

- kind: `function`
- signature: `is_worker()`

Return True when running inside a Seamless worker process.

## `seamless.register_close_hook`

- kind: `function`
- signature: `register_close_hook(hook)`

Register a callable to be run when seamless.close() executes.

## `seamless.set_is_worker`

- kind: `function`
- signature: `set_is_worker(value)`

Mark the current process as a Seamless worker process.
