# seamless.buffer_class

Class for Seamless buffers.

## `seamless.buffer_class.Buffer`

- kind: `class`
- signature: `Buffer`

Class for Seamless buffers.

## `seamless.buffer_class.Buffer.checksum`

- kind: `method`
- signature: `checksum(self)`

Returns the buffer's Checksum object, which must have been calculated already

## `seamless.buffer_class.Buffer.content`

- kind: `method`
- signature: `content(self)`

Return the buffer value

## `seamless.buffer_class.Buffer.decode`

- kind: `method`
- signature: `decode(self)`

_No docstring._

## `seamless.buffer_class.Buffer.decref`

- kind: `method`
- signature: `decref(self)`

Decrement normal refcount in the buffer cache. If no refs remain (and no tempref), may be uncached.

## `seamless.buffer_class.Buffer.from_async`

- kind: `method`
- signature: `from_async(cls, value, celltype, *, use_cache, checksum)`

Init from value, asynchronously

## `seamless.buffer_class.Buffer.get_checksum`

- kind: `method`
- signature: `get_checksum(self)`

Returns the buffer's Checksum object, calculating it if needed

## `seamless.buffer_class.Buffer.get_checksum_async`

- kind: `method`
- signature: `get_checksum_async(self)`

Returns the buffer's Checksum object, calculating it asynchronously if needed

## `seamless.buffer_class.Buffer.get_value`

- kind: `method`
- signature: `get_value(self, celltype)`

Converts the buffer to a value.
The checksum must have been computed already.

## `seamless.buffer_class.Buffer.get_value_async`

- kind: `method`
- signature: `get_value_async(self, celltype, *, copy)`

Converts the buffer to a value.
The checksum must have been computed already.

If copy=False, the value can be returned from cache.
It must not be modified.

## `seamless.buffer_class.Buffer.incref`

- kind: `method`
- signature: `incref(self)`

Increment normal refcount in the buffer cache.

## `seamless.buffer_class.Buffer.load`

- kind: `method`
- signature: `load(cls, filename)`

Loads the buffer from a file

## `seamless.buffer_class.Buffer.save`

- kind: `method`
- signature: `save(self, filename)`

Saves the buffer to a file

## `seamless.buffer_class.Buffer.tempref`

- kind: `method`
- signature: `tempref(self, interest, fade_factor, fade_interval, scratch)`

Add or refresh a single tempref. Only one tempref allowed per checksum.

If scratch is True, keep the tempref scratch-only (no remote registration).

## `seamless.buffer_class.Buffer.write`

- kind: `method`
- signature: `write(self)`

Write the buffer to remote server(s), if any have been configured
Returns True if the write has succeeded.
