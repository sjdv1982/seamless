from collections import OrderedDict
import asyncio
import traceback

from .worker import Worker, InputPin, OutputPin
from .status import StatusReasonEnum

class Transformer(Worker):
    _checksum = None
    _prelim_result = False
    _progress = 0.0
    _env = None
    _meta = None
    _exception_to_clear = False
    _debug = None

    def __init__(self, transformer_params, *,  stream_params=None):
        self.code = InputPin(self, "code", "python", "transformer")
        self.META = InputPin(self, "META", "plain")
        self._pins = {"code":self.code, "META": self.META}
        self._output_name = None
        self._transformer_params = OrderedDict()
        self._stream_params = stream_params # TODO: validate
        forbidden = ("code","META")
        for p in sorted(transformer_params.keys()):
            if p in forbidden:
                raise ValueError("Forbidden pin name: %s" % p)
            param = transformer_params[p]
            self._transformer_params[p] = param
            pin = None
            io, celltype, subcelltype, as_ = None, None, None, None
            if isinstance(param, str):
                io = param
            elif isinstance(param, (list, tuple)):
                io = param[0]
                if len(param) > 1:
                    celltype = param[1]
                if len(param) > 2:
                    subcelltype = param[2]
                if len(param) > 3:
                    raise ValueError(param)
            elif isinstance(param, dict):
                io = param["io"]
                celltype = param.get("celltype", celltype)
                subcelltype = param.get("subcelltype", subcelltype)
                as_ = param.get("as", None)
            else:
                raise ValueError((p, param))
            if io == "input":
                pin = InputPin(self, p, celltype, subcelltype, as_=as_)
            elif io == "output":
                pin = OutputPin(self, p, celltype, subcelltype, as_=as_)
                assert self._output_name is None  # can have only one output
                self._output_name = p
            else:
                raise ValueError(io)

            if pin is not None:
                self._pins[p] = pin

        if self._output_name is None:
            raise Exception("Transformer must have an output")
        super().__init__()

    def _set_context(self, ctx, name):
        has_ctx = self._context is not None
        super()._set_context(ctx, name)
        if not has_ctx:
            self._get_manager().register_transformer(self)

    @property
    def env(self):
        return self._env

    @env.setter
    def env(self, env: dict):
        if not isinstance(env, dict):
            raise TypeError(type(env))
        self._env = env

    @property
    def meta(self):
        return self._meta

    @meta.setter
    def meta(self, meta: dict):
        if not isinstance(meta, dict):
            raise TypeError(type(meta))
        self._meta = meta

    @property
    def checksum(self):
        checksum = self._checksum
        if checksum is not None:
            checksum = checksum.hex()
        return checksum

    @property
    def void(self):
        return self._void

    @property
    def preliminary(self):
        if self._void:
            return False
        if self._prelim_result:
            return True
        manager = self._get_manager()
        livegraph = manager.livegraph
        upstreams = livegraph.transformer_to_upstream.get(self)
        if upstreams is not None:
            for accessor in upstreams.values():
                if accessor is None:
                    continue
                if accessor.preliminary:
                    return True
        return False

    def get_transformation(self):
        import asyncio
        assert not asyncio.get_event_loop().is_running()
        from .manager.tasks.transformer_update import TransformerUpdateTask
        manager = self._get_manager()
        taskmanager = manager.taskmanager
        async def await_transformer():
            while 1:
                for task in taskmanager.transformer_to_task[self]:
                    if not isinstance(task, TransformerUpdateTask):
                        break
                    if not task.waiting_for_job:
                        break
                else:
                    break
                await asyncio.sleep(0.05)
        fut = asyncio.ensure_future(await_transformer())
        asyncio.get_event_loop().run_until_complete(fut)
        tcache = manager.cachemanager.transformation_cache
        checksum = tcache.transformer_to_transformations.get(self)
        if checksum is not None:
            checksum = checksum.hex()
        return checksum

    def clear_exception(self):
        manager = self._get_manager()
        tcache = manager.cachemanager.transformation_cache
        tcache.clear_exception(self)

    def cancel(self):
        manager = self._get_manager()
        tcache = manager.cachemanager.transformation_cache
        tcache.hard_cancel(self)

    def shell(self):
        raise NotImplementedError

    def _get_status(self):
        from .status import status_transformer
        status = status_transformer(self)
        return status

    @property
    def status(self):
        """The computation status of the transformer"""
        from .status import format_worker_status
        status = self._get_status()
        statustxt = format_worker_status(status)
        return "Status: " + statustxt

    @property
    def exception(self):
        from .transformation import RemoteJobError, SeamlessTransformationError, SeamlessStreamTransformationError
        if not self._void:
            return None
        if self._status_reason == StatusReasonEnum.INVALID:
            livegraph = self._get_manager().livegraph
            upstreams = livegraph.transformer_to_upstream.get(self)
            exceptions = {}
            if upstreams is not None:
                for pinname, accessor in upstreams.items():
                    if accessor is None: #unconnected
                        continue
                    exc = accessor.exception
                    if exc is not None:
                        exceptions[pinname] = exc
            if not len(exceptions):
                return None
            return exceptions
        if self._status_reason != StatusReasonEnum.ERROR:
            return None
        manager = self._get_manager()
        transformation_cache = manager.cachemanager.transformation_cache
        transformation = transformation_cache.transformer_to_transformations.get(self)
        if transformation is None:
            return None
        exc = transformation_cache.transformation_exceptions.get(transformation)
        if exc is None:
            return None
        if isinstance(exc, (RemoteJobError, SeamlessTransformationError, SeamlessStreamTransformationError)):
            return exc.args[0]
        s = traceback.format_exception(
            value=exc,
            etype=type(exc),
            tb=exc.__traceback__
        )
        return "".join(s)

    @property
    def logs(self):
        from .transformation import RemoteJobError, SeamlessTransformationError, SeamlessStreamTransformationError
        manager = self._get_manager()
        transformation_cache = manager.cachemanager.transformation_cache
        transformation = transformation_cache.transformer_to_transformations.get(self)
        if transformation is None:
            return None
        logs = transformation_cache.transformation_logs.get(transformation)
        if logs is not None:
            return logs

        exc = transformation_cache.transformation_exceptions.get(transformation)
        if exc is None:
            return None
        if isinstance(exc, (RemoteJobError, SeamlessTransformationError, SeamlessStreamTransformationError)):
            return exc.args[0]
        s = traceback.format_exception(
            value=exc,
            etype=type(exc),
            tb=exc.__traceback__
        )
        return "".join(s)

    @property
    def void(self):
        return self._void

    def _get_buffer_sync(self):
        from .protocol.get_buffer import get_buffer
        if self._checksum is None:
            return None
        buffer = get_buffer(self._checksum)
        return buffer

    async def _get_buffer(self):
        from .protocol.get_buffer import get_buffer
        if self._checksum is None:
            return None
        cachemanager = self._get_manager().cachemanager
        buffer = await cachemanager.fingertip(self._checksum)
        return buffer

    async def _get_value(self):
        from .protocol.deserialize import deserialize
        manager = self._get_manager()
        livegraph = manager.livegraph
        downstreams = livegraph.transformer_to_downstream[self]
        if not len(downstreams):
            return None
        first_output = downstreams[0].write_accessor.target()
        outputpin = self._pins[self._output_name]
        output_celltype = outputpin.celltype
        if output_celltype is None:
            output_celltype = first_output._celltype
        checksum = self._checksum
        buffer = await self._get_buffer()
        if buffer is None:
            return None
        value = await deserialize(buffer, checksum, output_celltype, True)
        return value

    def _get_value_sync(self):
        from .protocol.deserialize import deserialize_sync
        manager = self._get_manager()
        livegraph = manager.livegraph
        downstreams = livegraph.transformer_to_downstream[self]
        if not len(downstreams):
            return None
        first_output = downstreams[0].write_accessor.target()
        outputpin = self._pins[self._output_name]
        output_celltype = outputpin.celltype
        if output_celltype is None:
            output_celltype = first_output._celltype
        checksum = self._checksum
        buffer = self._get_buffer_sync()
        if buffer is None:
            return None
        value = deserialize_sync(buffer, checksum, output_celltype, True)
        return value

    @property
    def buffer(self):
        if asyncio.get_event_loop().is_running():
            return self._get_buffer_sync()
        task = self._get_buffer()
        loop = asyncio.get_event_loop()
        future = asyncio.ensure_future(task)
        loop.run_until_complete(future)
        return future.result()

    @property
    def value(self):
        if asyncio.get_event_loop().is_running():
            return self._get_value_sync()
        task = self._get_value()
        loop = asyncio.get_event_loop()
        future = asyncio.ensure_future(task)
        loop.run_until_complete(future)
        return future.result()

    def destroy(self, *, from_del=False):
        self._get_manager()._destroy_transformer(self)
        super().destroy(from_del=from_del)

    def __str__(self):
        ret = "Seamless transformer: " + self._format_path()
        return ret

def transformer(params, *, stream_params=None):
    """Defines a transformer.

Transformers transform their input cells into an output result.
Transformers are connected to their input cells via input pins, and their
result is connected to an output cell via an output pin. There can be only one
output pin. The pins are declared in the `params` parameter (see below).

In addition, all transformers have an implicit input pin named "code",
which must be connected to a Python cell.
All input values are injected directly into the code's namespace. The variable
name of the input is the same as its pin name.

Transformers are asynchronous (non-blocking),
and they carry out their computation in a separate process
(using ``multiprocessing``).

Transformers start their computation as soon as all inputs
(including the code) has been defined, even if no output cell has been connected.
Whenever the input data or code changes, a new computation is performed. If the
previous computation is still in progress, it is canceled.

Inside the transformer code, preliminary values can be returned using
``return_preliminary(value)``.

Invoke ``transformer.status()`` to get the current status of the transformer.

``pin.connect(cell)`` connects an outputpin to a cell.

``cell.connect(pin)`` connects a cell to an inputpin.

``pin.cell()`` returns or creates a cell that is connected to that pin.

Parameters
----------

    params: dict
        A dictionary containing the transformer parameters.

        Each (name,value) item represents a transformer pin:

        -  name: string
            name of the pin

        -  value: dict
            with the following items:

            - pin: string
                must be "input" or "output". Only one output pin is allowed.
            - dtype: string or tuple of strings
                Describes the type of the cell(s) connected to the pin.
    """
    return Transformer(params, stream_params=stream_params)
