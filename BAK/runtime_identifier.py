from weakref import WeakValueDictionary, WeakKeyDictionary

_runtime_identifiers = WeakValueDictionary()
_runtime_identifiers_rev = WeakKeyDictionary()

def get_runtime_identifier(worker):
    identifier = worker._format_path()
    holder = _runtime_identifiers.get(identifier, None)
    if holder is None:
        _runtime_identifiers[identifier] = worker
        if worker in _runtime_identifiers_rev:
            old_identifier = _runtime_identifiers_rev.pop(worker)
            _runtime_identifiers.pop(old_identifier)
        _runtime_identifiers_rev[worker] = identifier
        return identifier
    elif holder is worker:
        return identifier
    elif worker in _runtime_identifiers_rev:
        return _runtime_identifiers_rev[worker]
    else:
        count = 0
        while True:
            count += 1
            new_identifier = identifier + "-" + str(count)
            if new_identifier not in _runtime_identifiers:
                break
        _runtime_identifiers[new_identifier] = worker
        _runtime_identifiers_rev[worker] = new_identifier
        return new_identifier
