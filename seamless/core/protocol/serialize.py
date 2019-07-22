from ...pylru import lrucache

serialize_cache = lrucache(100)

def serialize(value, celltype):
    idvalue = id(value) 
    result = serialize_cache.get(idvalue)
    if result is not None:
        return result
    if celltype != "text": raise NotImplementedError #livegraph branch
    result = value
    
    serialize_cache[idvalue] = result
    return result