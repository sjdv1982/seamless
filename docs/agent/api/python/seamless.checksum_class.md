# seamless.checksum_class

Class for Seamless checksums. Seamless checksums are calculated as SHA-256 hashes of buffers.

## `seamless.checksum_class.Checksum`

- kind: `class`
- signature: `Checksum`

Class for Seamless checksums.
Seamless checksums are calculated as SHA-256 hashes of buffers.

## `seamless.checksum_class.Checksum.bytes`

- kind: `method`
- signature: `bytes(self)`

Returns the checksum as a 32-byte bytes object

## `seamless.checksum_class.Checksum.decref`

- kind: `method`
- signature: `decref(self)`

Decrement normal refcount in the buffer cache. If no refs remain (and no tempref), may be uncached.

## `seamless.checksum_class.Checksum.find`

- kind: `method`
- signature: `find(self, verbose)`

Returns a list of URL infos to download the underlying buffer.
An URL info can be an URL string, or a dict with additional information.

## `seamless.checksum_class.Checksum.fingertip`

- kind: `method`
- signature: `fingertip(self, celltype)`

Return a resolvable buffer/value, recomputing locally if needed.

## `seamless.checksum_class.Checksum.fingertip_sync`

- kind: `method`
- signature: `fingertip_sync(self, celltype)`

Synchronously resolve or recompute the checksum buffer/value.

## `seamless.checksum_class.Checksum.hex`

- kind: `method`
- signature: `hex(self)`

Returns the checksum as a 64-byte hexadecimal string

## `seamless.checksum_class.Checksum.incref`

- kind: `method`
- signature: `incref(self, *, scratch)`

Increment normal refcount in the buffer cache.

If scratch is True, keep the ref scratch-only (no remote registration).

## `seamless.checksum_class.Checksum.load`

- kind: `method`
- signature: `load(cls, filename)`

Loads the checksum from a .CHECKSUM file.

If the filename doesn't have a .CHECKSUM extension, it is added

## `seamless.checksum_class.Checksum.resolution`

- kind: `method`
- signature: `resolution(self, celltype)`

Returns the data buffer that corresponds to the checksum.
If celltype is provided, a value is returned instead.

## `seamless.checksum_class.Checksum.resolve`

- kind: `method`
- signature: `resolve(self, celltype)`

Returns the data buffer that corresponds to the checksum.
If celltype is provided, a value is returned instead.

The buffer is retrieved from buffer cache

## `seamless.checksum_class.Checksum.save`

- kind: `method`
- signature: `save(self, filename)`

Saves the checksum to a .CHECKSUM file.

If the filename doesn't have a .CHECKSUM extension, it is added

## `seamless.checksum_class.Checksum.tempref`

- kind: `method`
- signature: `tempref(self, interest, fade_factor, fade_interval, scratch)`

Add or refresh a single tempref. Only one tempref allowed per checksum.

If scratch is True, keep the tempref scratch-only (no remote registration).

## `seamless.checksum_class._run_coro_in_new_loop`

- kind: `function`
- signature: `_run_coro_in_new_loop(coro)`

_No docstring._

## `seamless.checksum_class._run_coro_in_worker_thread`

- kind: `function`
- signature: `_run_coro_in_worker_thread(coro)`

_No docstring._

## `seamless.checksum_class.validate_checksum`

- kind: `function`
- signature: `validate_checksum(v)`

Validate a checksum, list or dict recursively
