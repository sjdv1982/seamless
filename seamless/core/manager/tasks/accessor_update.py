from . import Task

class AccessorUpdateTask(Task):
    def __init__(self, manager, accessor):
        assert isinstance(accessor, ReadAccessor)
        self.accessor = accessor
        super().__init__(manager)
        self.dependencies.append(accessor)

    async def _run(self):
        accessor = self.accessor

        # Get the expression. If it is None, do an accessor void cancellation
        expression = accessor.expression
        manager = self.manager()

        if expression is None:
            accessor._status_reason = StatusReasonEnum.UNDEFINED
            accessor._new_macropath = False
            manager.cancel_accessor(
                accessor, void=True,
                origin_task=self
            )
            return

        expression_result_checksum = await EvaluateExpressionTask(manager, expression).run()

        # If the expression result is None, do an accessor void cancellation
        if expression_result_checksum is None:
            accessor._status_reason = StatusReasonEnum.INVALID
            manager.cancel_accessor(accessor, void=True, origin_task=self)
            return
        if accessor._checksum == expression_result_checksum:
            if not accessor._new_macropath:
                return
        accessor._checksum = expression_result_checksum
        accessor._void = False
        accessor._status_reason = None

        # Select the write accessor's target.
        target = accessor.write_accessor.target()
        if isinstance(target, MacroPath):
            target = target._cell
        if target is None:
            return

        locknr = await acquire_evaluation_lock(self)
        try:
            accessor._new_macropath = False
            if isinstance(target, Worker):
                worker = target
                # If a worker, launch a worker update task. The worker will retrieve the upstream checksums by itself.
                if isinstance(worker, Transformer):
                    TransformerUpdateTask(manager, worker).launch()
                elif isinstance(worker, Reactor):
                    ReactorUpdateTask(manager, worker).launch()
                elif isinstance(worker, Macro):
                    MacroUpdateTask(manager, worker).launch()
                else:
                    raise TypeError(type(worker))
            elif isinstance(target, Cell): # If a cell:
                """
                if (str(target).find("CONNECTION_1") > -1 or str(target).find("CONNECTION_2") > -1):
                    e00 = expression_result_checksum
                    if e00 is not None:
                        e00 = e00.hex()
                    ctx = list(manager.contexts)[0]
                    cs00 = ctx.data_a._data._checksum
                    if cs00 is not None: cs00 = cs00.hex()
                    cs01 = ctx.data_b._data._checksum
                    if cs01 is not None: cs01 = cs01.hex()
                    print("ACCESSOR SET", target, e00[:10], expression.checksum.hex()[:10], str(cs00)[:10], str(cs01)[:10], hex(id(ctx.data_a)), hex(id(ctx.data_b)))
                """
                result_checksum = expression_result_checksum
                result_hash_pattern = expression.result_hash_pattern
                if result_hash_pattern == "#":
                    result_hash_pattern = None  # equivalent
                path = accessor.write_accessor.path
                target_hash_pattern = target._hash_pattern
                if path is not None and target_hash_pattern is not None:
                    target_hash_pattern = access_hash_pattern(target_hash_pattern, path)
                ### Code below is for simple hash patterns.
                # More complex hash patterns may be also be equivalent, which can be determined:
                # - Statically, e.g. {"x": "#"} == {"*": "#"}
                # - Dynamically, e.g. {"x": "#", "y": {"!": "#"} } == {"x": "#"} if y is absent in the value
                # This is to be implemented later.

                if result_checksum is not None and result_hash_pattern != target_hash_pattern:
                    if result_hash_pattern is None:
                        if target_hash_pattern == "#":
                            pass
                        else:
                            # re-encode with target hash pattern
                            new_result_checksum = await apply_hash_pattern(result_checksum, target_hash_pattern)
                            result_checksum = new_result_checksum
                    else:
                        result_buffer = await GetBufferTask(manager, result_checksum).run()
                        if result_buffer is None:
                            raise CacheMissError(result_checksum)
                        deep_result_value = await DeserializeBufferTask(manager, result_buffer, result_checksum, "plain", False).run()
                        mode, subpath_result = await get_subpath(deep_result_value, result_hash_pattern, ())
                        if mode == "checksum":
                            raise ValueError(result_hash_pattern) # should have been '#'
                        new_result_value = subpath_result
                        if target_hash_pattern is None or target_hash_pattern == "#":
                            target_buffer = await SerializeToBufferTask(manager, new_result_value, "mixed", True).run()
                        else:
                            target_deep_value , _ = await value_to_deep_structure(new_result_value, target_hash_pattern)
                            target_buffer = await SerializeToBufferTask(manager, target_deep_value, "mixed", True).run()
                        target_checksum = await CalculateChecksumTask(manager, target_buffer).run()
                        buffer_cache.cache_buffer(target_checksum, target_buffer)
                        result_checksum = target_checksum
                ###

                if path is None:
                    await manager.taskmanager.await_upon_connection_tasks(self.taskid, target._root())
                    manager._set_cell_checksum(
                        target, result_checksum,
                        False, None, prelim=accessor._prelim
                    )
                    CellUpdateTask(manager, target).launch()
                else:
                    if not target._destroyed:
                        assert expression.target_celltype == "mixed", expression.target_celltype
                        sc = target._structured_cell
                        assert sc is not None
                        inchannel = sc.inchannels[path]
                        manager._set_inchannel_checksum(
                            inchannel, result_checksum,
                            False, None, prelim=accessor._prelim
                        )
            else:
                raise TypeError(target)
        finally:
            release_evaluation_lock(locknr)

from ..accessor import ReadAccessor
from .evaluate_expression import EvaluateExpressionTask
from .transformer_update import TransformerUpdateTask
from .reactor_update import ReactorUpdateTask
from .macro_update import MacroUpdateTask
from .cell_update import CellUpdateTask
from .get_buffer import GetBufferTask
from .serialize_buffer import SerializeToBufferTask
from .deserialize_buffer import DeserializeBufferTask
from .checksum import CalculateChecksumTask
from ...worker import Worker
from ...transformer import Transformer
from ...reactor import Reactor
from ...macro import Macro, Path as MacroPath
from ...cell import Cell
from ...status import StatusReasonEnum
from ...cache import CacheMissError
from ...cache.buffer_cache import buffer_cache
from ...protocol.deep_structure import access_hash_pattern, apply_hash_pattern, value_to_deep_structure
from ...protocol.expression import get_subpath
from . import acquire_evaluation_lock, release_evaluation_lock