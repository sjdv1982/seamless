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