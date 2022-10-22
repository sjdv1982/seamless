def merge_subresults_list(**subresults):
    result = []
    for k in sorted(subresults.keys()):
        v = subresults[k]
        result += v
    return result

def merge_subresults_dict(**subresults):
    result = {}
    for sub in subresults.values():
        result.update(sub)
    return result

def merge_subresults_chunk(subresults):
    result = {}
    for sub in subresults:
        result.update(sub)
    return result

def merge_subresults_chunk_list(subresults):
    import numpy as np
    import itertools
    first_type, first_dtype = None, None
    first = True
    totlen = 0
    for vnr, v in enumerate(subresults):
        if (v == []) is True:
            continue
        v_type = type(v)
        v_dtype = None
        if issubclass(v_type, np.ndarray):
            if not len(v):
                continue
            if v.ndim != 1:
                raise TypeError("Merged subresult '{}' numpy array must be one-dimensional".format(vnr))
            v_dtype = v.dtype
        elif issubclass(v_type, list):
            if not len(v):
                continue
        else:
            try:
                if not len(v):
                    continue
            except Exception:
                pass
            raise TypeError("Merged subresult '{}' must be list or numpy array, not {}".format(vnr, v_type))
        
        if first:
            first_type = v_type
            first_dtype = v_dtype
            first_vnr = vnr
            first = False
        else:
            if v_type != first_type:
                raise TypeError("Type mismatch between subresults '{}' and '{}': {} vs {}".format(first_vnr, vnr, first_type, v_type))
            if v_dtype != first_dtype:
                raise TypeError("Numpy dtype mismatch between subresults '{}' and '{}': {} vs {}".format(first_vnr, vnr, first_dtype, v_dtype))
        
        totlen += len(v)

    if first_type is None:  # all subresults are empty lists
        return []

    if issubclass(v_type, np.ndarray):
        result = np.empty(totlen, v_dtype)
        currlen = 0
        for v in subresults:
            if not len(v):
                continue
            newlen = currlen + len(v)
            result[currlen:newlen] = v
            currlen = newlen
    else:
        result = list(itertools.chain(*subresults))
    return result

def calc_keyorder(inp_, keyorder0):
    result = []
    done = set()
    for k in keyorder0:
        if k in inp_:
            result.append(k)
            done.add(k)
    for k in inp_:
        if k not in done:
            result.append(k)
    return result