import asyncio
import json
import traceback

from ..cache.buffer_cache import buffer_cache

class FingerTipper:
    """Short-lived object to perform nested fingertipping"""
    def __init__(self, checksum, cachemanager, *, done):
        from seamless.util import is_forked
        self.checksum = checksum
        self.cachemanager = cachemanager
        self.done = done
        self.clear()
        self.manager = cachemanager.manager()
        self.tf_cache = cachemanager.transformation_cache
        self.is_forked = is_forked()

    def clear(self):
        """Clear the fingertipping tasks"""
        self.transformations = []
        self.expressions = []
        self.joins = []
        self.joins2 = []   # by checksum
        self.syn2sem = []

    @property
    def empty(self):
        return (not self.transformations) and (not self.expressions) and (not self.joins) and (not self.joins2) and (not self.syn2sem)

    async def fingertip_upstream(self, checksum):
        return await self.cachemanager._fingertip(checksum, must_have_cell=False, done=self.done)

    async def fingertip_transformation(self, transformation, tf_checksum):
        from ..direct.run import run_transformation_dict
        coros = []
        for pinname in transformation:
            if pinname == "__env__":
                cs = bytes.fromhex(transformation[pinname])
                coros.append(self.fingertip_upstream(cs))
                continue
            if pinname.startswith("__"):
                continue
            celltype, subcelltype, sem_checksum0 = transformation[pinname]
            sem_checksum = bytes.fromhex(sem_checksum0) if sem_checksum0 is not None else None
            sem2syn = self.tf_cache.semantic_to_syntactic_checksums
            semkey = (sem_checksum, celltype, subcelltype)
            checksum2 = sem2syn.get(semkey, [sem_checksum])[0]
            coros.append(self.fingertip_upstream(checksum2))
        try:   
            await asyncio.gather(*coros)
        except asyncio.CancelledError as exc:
            for coro in coros:
                coro.cancel()
            raise exc from None
        
        if self.is_forked:
            run_transformation_dict(transformation, fingertip=True)
        else:
            job = self.tf_cache.run_job(transformation, tf_checksum, scratch=True, fingertip=True)
            if job is not None:
                await asyncio.shield(job.future)

    async def fingertip_expression(self, expression):
        from .tasks.evaluate_expression import evaluate_expression
        await self.fingertip_upstream(expression.checksum)
        await evaluate_expression(
            expression, manager=self.manager, fingertip_mode=True
        )

    def _register(self, buf):
        if buf is not None:
            checksum0 = calculate_checksum(buf)
            if checksum0 == self.checksum:
                buffer_cache.cache_buffer(self.checksum, buf)

    async def fingertip_join(self, join_dict):
        from .tasks.deserialize_buffer import DeserializeBufferTask
        from .tasks.serialize_buffer import SerializeToBufferTask
        hash_pattern = join_dict.get("hash_pattern")
        inchannels0 = join_dict["inchannels"]
        inchannels = {}
        for path0, cs in inchannels0.items():
            path = json.loads(path0)
            if isinstance(path, list):
                path = tuple(path)
            inchannels[path] = cs
        paths = sorted(list(inchannels.keys()))
        if "auth" in join_dict:
            auth_checksum = bytes.fromhex(join_dict["auth"])
            auth_buffer = await self.fingertip_upstream(auth_checksum)
            value = await DeserializeBufferTask(
                self.manager, auth_buffer, auth_checksum, "mixed", copy=True
            ).run()
        else:
            if isinstance(paths[0], int):
                value = []
            elif isinstance(paths[0], (list, tuple)) and len(paths[0]) and isinstance(paths[0][0], int):
                value = []
            else:
                value = None
                if hash_pattern is not None:
                    if isinstance(hash_pattern, dict):
                        for k in hash_pattern:
                            if k.startswith("!"):
                                value = []
                                break
                if value is None:
                    value = {}
        for path in paths:
            subchecksum = bytes.fromhex(inchannels[path])
            sub_buffer = None
            if hash_pattern is None or access_hash_pattern(hash_pattern, path) not in ("#", '##'):
                sub_buffer = await self.fingertip_upstream(subchecksum)
            await set_subpath_checksum(value, hash_pattern, path, subchecksum, sub_buffer)
        buf = await SerializeToBufferTask(
            self.manager, value, "mixed",
            use_cache=True
        ).run()
        self._register(buf)

    async def fingertip_join2(self, join_dict_checksum):
        join_buf = await self.fingertip_upstream(join_dict_checksum)
        if join_buf is None:
            return
        join_dict = json.loads(join_buf.decode())
        if not isinstance(join_dict, dict):
            raise TypeError(type(join_dict))
        return await self.fingertip_join(join_dict)

    async def fingertip_syn2sem(self, syn_checksum, celltype, subcelltype):
        await syntactic_to_semantic(syn_checksum, celltype, subcelltype, "fingertip")
        buf = get_buffer(self.checksum, remote=False)
        self._register(buf)

    async def run(self):
        """Runs the fingertipping tasks. Returns None if successful.
        Otherwise, runs the task exceptions"""
        if self.empty:
            return

        self.transformations[:] = list({v:(k,v) for k,v in self.transformations}.values())
        coros = []
        for transformation, tf_checksum in self.transformations:
            coro = self.fingertip_transformation(transformation, tf_checksum)
            coros.append(coro)
        for expression in self.expressions:
            coro = self.fingertip_expression(expression)
            coros.append(coro)
        for join_dict in self.joins:
            coro = self.fingertip_join(join_dict)
            coros.append(coro)
        for join_dict_checksum in self.joins2:
            coro = self.fingertip_join2(join_dict_checksum)
            coros.append(coro)
        for syn_checksum, celltype, subcelltype in self.syn2sem:
            coro = self.fingertip_syn2sem(syn_checksum, celltype, subcelltype)
            coros.append(coro)

        all_tasks = [asyncio.ensure_future(c) for c in coros]
        try:
            tasks = all_tasks
            while len(tasks):
                _, tasks  = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                buffer = get_buffer(self.checksum, remote=False)
                if buffer is not None:
                    return
        finally:
            for task in all_tasks:
                if task.done():
                    try:
                        task.result()
                    except Exception:
                        #import traceback; traceback.print_exc()
                        pass
                else:
                    task.cancel()

        exc_list = ["\n".join(traceback.format_exception(task.exception())) for task in all_tasks if task.exception()]
        exc_str = ""
        if len(exc_list):
            exc_str = "\nFingertip exceptions:\n\n" + "\n\n".join(exc_list)
        return exc_str


from ..protocol.expression import set_subpath_checksum, access_hash_pattern
from ..protocol.get_buffer import get_buffer
from ..cache.transformation_cache import syntactic_to_semantic
from ... import calculate_checksum