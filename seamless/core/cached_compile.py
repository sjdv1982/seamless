import linecache


def cached_compile(code, identifier, mode="exec", flags=None, \
  dont_inherit=0):
    if flags is not None:
        ast = compile(code, identifier, mode, flags, dont_inherit)
    else:
        ast = compile(code, identifier, mode, dont_inherit=dont_inherit)
    cache_entry = (
        len(code), None,
        [line+'\n' for line in code.splitlines()], identifier
    )
    linecache.cache[identifier] = cache_entry
    return ast
