from ast import FunctionDef, Return, iter_child_nodes
from collections import OrderedDict

def strip_source(source):
    indent = None
    for l in source.splitlines():
        i = len(l) - len(l.lstrip())
        if indent is None or i < indent:
            indent = i
    if indent is None:
        return source
    ret = ""
    for l in source.splitlines():
        ret += l[indent:] + "\n"
    return ret

def ordered_dictsort(data):
    for k, v in list(data.items()):
        if isinstance(v, OrderedDict):
            ordered_dictsort(v)
        elif isinstance(v, dict):
            data[k] = dictsort(v)
        elif isinstance(v, tuple):
            data[k] = tuplesort(v)
        elif isinstance(v, list):
            listsort(v)

def listsort(data):
    for vnr in range(len(data)):
        v = data[vnr]
        if isinstance(v, OrderedDict):
            ordered_dictsort(v)
        elif isinstance(v, dict):
            data[vnr] = dictsort(v)
        elif isinstance(v, tuple):
            data[vnr] = tuplesort(v)
        elif isinstance(v, list):
            listsort(v)

def tuplesort(data):
    ret = []
    for v in data:
        if isinstance(v, OrderedDict):
            ordered_dictsort(v)
        elif isinstance(v, dict):
            v = dictsort(v)
        elif isinstance(v, tuple):
            v = tuplesort(v)
        elif isinstance(v, list):
            listsort(v)
        ret.append(v)
    return ret

def dictsort(data):
    ret = OrderedDict()
    for k in sorted(data.keys()):
        v = data[k]
        if isinstance(v, OrderedDict):
            ordered_dictsort(v)
        elif isinstance(v, dict):
            v = dictsort(v)
        elif isinstance(v, tuple):
            v = tuplesort(v)
        elif isinstance(v, list):
            listsort(v)
        ret[k] = v
    return ret

def overlap_path(p1, p2):
    if p1[:len(p2)] == p2:
        return True
    elif p2[:len(p1)] == p1:
        return True
    else:
        return False
