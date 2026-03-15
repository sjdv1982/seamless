Worker spawning specification
=============================

The submodule `seamless_transformer.worker` has a function `spawn()`.
It takes an optional argument N which is the numbers of workers to spawn, by default this is the number of processes on the machine.
The spawning machinery and the communication between worker and parent is handled by the `seamless_transformer.process` submodule.

When called, spawn() fires up N workers. Each worker sets `set_is_worker(True)` and then listens forever (until shutdown request) for requests from the parent. Whenever a worker dies (segfaults), a new worker is spun up by the parent.

Parent requests are always Checksum objects, accompanied by two parameters: `scratch` (a bool) and `tf_dunder` (a dict). Whenever a checksum is received, the worker launches a thread that does the following:

- The checksum is resolved into a dict `.resolve(celltype="plain")`
- `/seamless1/seamless-transformer/seamless_transformer/run.py::run_transformation_dict` is called.
After the thread has ended,`.tempref()` is called on the result checksum. The result checksum is returned, or an exception traceback serialized as string. In the latter case, the parent process re-raises the exception in the caller frame that made the request.

In the parent process, a `has_spawned()` flag is set in `seamless_transformer.worker`. Future calls to `spawn()` check against this flag and raise a RuntimeError.
In `seamless_transformer/transformation_cache.py::run`, the local cache and database cache are
checked as usual (the database cache only if `is_worker` is False).
If they miss, the following code paths are considered:

- If `has_spawned()` is True:
    Assert that `is_worker` is False. Then, forward the call parameters (minus `require_value`) to the worker manager, awaiting the result.
    The manager will select one of the workers that has the least number of running requests, and send the request to that worker, and return the request checksum.

- If `is_worker` is True:
    Assert that `has_spawned()` is False. Then forward the call parameters (minus `require_value`) as a request to the parent process, awaiting the result.
    The parent process forwards this request to the worker manager, who will handle it as described above.
    The resulting transformation checksum or exception string is returned to the worker that made the request to the parent. Right before, in case of a transformation checksum, the parent does a `.tempref()` on the checksum.
    In case of an exception string, the worker re-raises the exception in the caller frame that made the request.

- If neither are true:
    Follow the default code path that calls `/seamless1/seamless-transformer/seamless_transformer/run.py::run_transformation_dict`

## Changes on the worker

1. In a worker, it is no longer possible to do Checksum.incref, .tempref, .decref the normal way. These methods become a no-op.
2. In a worker, it is also no longer possible to do Buffer.incref, .tempref, .decref the normal way. If these methods are
called, Buffer.get_checksum() gets invoked, and then the method becomes a request (request type "incref", "decref", or "tempref") to the parent, with the checksum and the buffer length as arguments.
Upon receiving such a request, The parent does Checksum.incref / .decref / .tempref on the received checksum.
In case of .decref, the parent simply returns afterwards.
In case of .incref, .tempref:
    - The parent returns 0 if the buffer is already in local buffer cache
    - Otherwise, it allocates and returns a shared memory pointer. The worker must copy the buffer into
      this shared memory location, and then make an "upload" request (with the pointer as an argument) to the parent.

Whenever the parent receives an "upload" request, it tracks down which checksum and buffer length correspond to the pointer. It constructs then a Buffer object from the shared memory
location.

Finally, in a worker, it is no longer possible to do Checksum.resolve() the normal way. If this
method is called, it sends a "download" request to the parent, with the checksum as argument.
The parent process resolves the buffer, allocates a shared memory pointer, and copies the buffer
into it. It returns then the pointer (including the buffer length). Upon receiving this response, the worker then creates a Buffer from the shared memory pointer. From this Buffer, a Checksum.resolve() return value is constructed as usual (either the Buffer itself or `Buffer.get_value(celltype)`).
Finally, a "downloaded" request is made to the parent, containing the shared pointer. Upon receiving a "downloaded" request, the parent frees the shared memory pointer.
