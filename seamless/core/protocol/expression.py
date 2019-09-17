def _set_subpath(value, path, subvalue):
    head = path[0]
    if len(path) == 1:
        value[head] = subvalue
        return
    if head not in value:
        head2 = path[1]
        if isinstance(head2, int):
            value[head] = []
        elif isinstance(head2, str):
            value[head] = {}
    sub_curr_value = value[head]
    _set_subpath(sub_curr_value, path[1:], subvalue)

def _get_subpath(value, path):
    if value is None:
        return None
    if not len(path):
        return value
    head = path[0]
    sub_curr_value = value[head]
    return _get_subpath(sub_curr_value, path[1:])

def get_subpath_sync(value, hash_pattern, path):
    if hash_pattern is not None:
        raise NotImplementedError
    return _get_subpath(value, path)

def set_subpath_sync(value, hash_pattern, path, subvalue):
    if hash_pattern is not None:
        raise NotImplementedError
    _set_subpath(value, path, subvalue)