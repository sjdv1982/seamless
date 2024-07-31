def run_transformation(checksum, *, fingertip=False, scratch=False, tf_dunder=None, new_event_loop=False, manager=None):
    from seamless.config import check_delegation
    from seamless.util import is_forked
    from .core.cache.transformation_cache import transformation_cache
    check_delegation()
    if running_in_jupyter and not new_event_loop:
        raise RuntimeError("'run_transformation' cannot be called from within Jupyter. Use 'await run_transformation_async' instead")
    elif asyncio.get_event_loop().is_running():
        if is_forked():
            # Allow it for forked processes (a new event loop will be launched)
            pass
        elif new_event_loop:
            # a new event loop will be launched anyway
            pass
        else:
            raise RuntimeError("'run_transformation' cannot be called from within a coroutine. Use 'await run_transformation_async' instead")

    if manager is None:
        tf_cache = transformation_cache
    else:
        tf_cache = manager.cachemanager.transformation_cache
    checksum = parse_checksum(checksum, as_bytes=True)
    tf_cache.transformation_exceptions.pop(checksum, None)
    return tf_cache.run_transformation(checksum, fingertip=fingertip, scratch=scratch, tf_dunder=tf_dunder, new_event_loop=new_event_loop, manager=manager)

async def run_transformation_async(checksum, *, fingertip, scratch, tf_dunder=None, manager=None, cache_only=False):
    from seamless.config import check_delegation
    from .core.cache.transformation_cache import transformation_cache
    check_delegation()
    checksum = parse_checksum(checksum, as_bytes=True)
    if manager is None:
        tf_cache = transformation_cache
    else:
        tf_cache = manager.cachemanager.transformation_cache
    checksum = parse_checksum(checksum, as_bytes=True)
    tf_cache.transformation_exceptions.pop(checksum, None)
    return await tf_cache.run_transformation_async(checksum, fingertip=fingertip, scratch=scratch, tf_dunder=tf_dunder, manager=manager, cache_only=cache_only)
