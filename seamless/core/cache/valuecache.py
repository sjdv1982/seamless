import weakref
from weakref import WeakValueDictionary

class ValueCache:
    """Checksum-to-value cache. 
    Every value is refered to by a tree (or more than one); non-tree values are 
    cached elsewhere.
    
    Memory intensive. Like any other cache, does not persist unless offloaded.
    Cache comes in two flavors: buffer cache and object cache.
    Buffer cache items are directly serializable, and can be shared over the 
    network, or offloaded to Redis.
     Keys are straightforward buffer checksums.
     Each item has two refcounts, authoritative and non-authoritative, 
     corresponding to the authority of refering tree(s).
     Trees referring to structured-cells-with-partial-authority count as 
     authoritative.
    Object cache items contain Python objects. They are strictly local.      
     Keys are *semantic keys*: consisting of a *semantic checksum* (i.e. 
     different from the buffer checksum in case of CSON and Python code trees),
     an access type, and a content type.
     They are maintained as a WeakValueDictionary, i.e. they get auto-cleaned-up 
     if Python holds no reference to them.
     A worker that accesses them gets a Python reference.
     cell.value gets a Python reference too, for non-structured cells.
     Structured cells (.value, .data, .handle) do NOT get a Python reference; 
      instead, the underlying Monitor gets backed up by an API that retrieves 
      the value from object cache when needed (and does not store it)
    There are two ways an item can be requested:
    1. Explicitly from object cache or buffer cache, using a semantic key resp. 
      a buffer checksum
    2. Items can be requested using a tree, from which the buffer checksum can be
     extracted, and a semantic key be generated or read from cache.
    Whenever a item is requested from object cache that is a partial miss 
     (a miss from object cache but a hit from buffer cache), the item gets 
     generated from buffer cache.
     In this case, and also if a new object item is added explicitly, 
     a temporary reference to  the item is added, that expires after 20 seconds.

    For cells, there is normally only one buffer cache item, because all trees 
     of the same cell._storage_type are mapped to it.
    In contrast, every tree typically has its own semantic checksum (reflecting
     both cell type and subpath), and therefore its own object cache item.
    """
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.buffer_cache = {} #buffer-checksum-to-value
        self.object_cache = WeakValueDictionary() #semantic-key-to-value

        # TODO: caches for annotation purposes: reverse caches, ...

"""
NOTE: value caches coming from treelevel>0 or from streams will never be 
auto-removed if their cell value changes. Non-authoritative cells may expire,
but authoritative values will now always be kept. """