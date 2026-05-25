# Streaming (Contract)

Streaming is an opt-in operational feature for `remote: daskserver`
transformations.

Enable it per transformation:

```python
tf.streaming = True
```

The flag is read at submission time. Changing it after `.compute()`, `.run()`,
`.start()`, or `.task()` has submitted the transformation does not affect the
in-flight run.

Streaming does not change transformation identity:

- it is not written into the transformation dictionary
- it is not written into dunder fields such as `__meta__`, `__env__`, or
  `__compilation__`
- it does not change `tf_checksum`
- it does not change persistent cache identity

Cached runs do not stream. If a daskserver worker can return the result from
the database cache, the transformation completes immediately and emits no
stdout/stderr chunks. Use the existing scratch/rerun controls when a fresh
execution is required.

Current scope:

- captured: Python `sys.stdout` and `sys.stderr` writes from the child
  transformation process
- backend: `remote: daskserver` only
- not captured yet: compiled-language subprocess stdout/stderr that bypasses
  Python `sys.stdout` / `sys.stderr`

