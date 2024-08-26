"""Run transformations by interacting with seamless.workflow.core"""

import asyncio
from seamless import Checksum


def run_transformation(
    checksum: Checksum,
    *,
    fingertip=False,
    scratch=False,
    tf_dunder=None,
    new_event_loop=False,
    manager=None
):
    """Run transformations by interacting with seamless.workflow.core"""
    from seamless.workflow import running_in_jupyter
    from seamless.config import check_delegation
    from seamless.util.is_forked import is_forked
    from seamless.workflow.core.cache.transformation_cache import transformation_cache

    check_delegation()
    if running_in_jupyter and not new_event_loop:
        raise RuntimeError(
            # pylint: disable=line-too-long
            "'run_transformation' cannot be called from within Jupyter. Use 'await run_transformation_async' instead"
        )
    elif asyncio.get_event_loop().is_running():
        if is_forked():
            # Allow it for forked processes (a new event loop will be launched)
            pass
        elif new_event_loop:
            # a new event loop will be launched anyway
            pass
        else:
            raise RuntimeError(
                # pylint: disable=line-too-long
                "'run_transformation' cannot be called from within a coroutine. Use 'await run_transformation_async' instead"
            )

    if manager is None:
        tf_cache = transformation_cache
    else:
        tf_cache = manager.cachemanager.transformation_cache
    checksum = Checksum(checksum)
    tf_cache.transformation_exceptions.pop(checksum, None)
    return tf_cache.run_transformation(
        checksum,
        fingertip=fingertip,
        scratch=scratch,
        tf_dunder=tf_dunder,
        new_event_loop=new_event_loop,
        manager=manager,
    )


async def run_transformation_async(
    checksum: Checksum,
    *,
    fingertip,
    scratch,
    tf_dunder=None,
    manager=None,
    cache_only=False
):
    """Run transformations by interacting with seamless.workflow.core"""
    from seamless.config import check_delegation
    from seamless.workflow.core.cache.transformation_cache import transformation_cache

    check_delegation()
    checksum = Checksum(checksum)
    if manager is None:
        tf_cache = transformation_cache
    else:
        tf_cache = manager.cachemanager.transformation_cache
    tf_cache.transformation_exceptions.pop(checksum, None)
    return await tf_cache.run_transformation_async(
        checksum,
        fingertip=fingertip,
        scratch=scratch,
        tf_dunder=tf_dunder,
        manager=manager,
        cache_only=cache_only,
    )
