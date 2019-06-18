import time
import weakref
from weakref import WeakValueDictionary
import functools
from collections import namedtuple

from .redis_client import redis_sinks, redis_caches

NO_EXPIRE_SIZE_LIMIT = 1000000 ### TODO: configure this, also per-cell

class WeakrefableWrapper:
    __slots__ = ["value", "__weakref__"]
    def __init__(self, value):
        self.value = value

SemanticKey = namedtuple("SemanticKey", 
    ("semantic_checksum", "access_mode", "subpath")
)

value_caches = weakref.WeakSet()

class ValueCache:
    """Checksum-to-value cache.
    Every value is refered to by a expression (or more than one); non-expression values are
    cached elsewhere.

    Memory intensive. Like any other cache, does not persist unless offloaded.
    Cache comes in two flavors: buffer cache and object cache.
    Buffer cache items are directly serializable, and can be shared over the
    network, or offloaded to Redis.
     Keys are straightforward buffer checksums.
     Each item has two refcounts, authoritative and non-authoritative,
     corresponding to the authority of refering expression(s).
     Trees referring to structured-cells-with-partial-authority count as
     authoritative.
    Object cache items contain Python objects. They are strictly local.
     Keys are *semantic keys*: consisting of a *semantic checksum* (i.e.
     different from the buffer checksum in case of CSON and Python code expressions),
     an access mode, and a content type.
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
    2. Items can be requested using a expression, from which the buffer checksum can be
     extracted, and a semantic key be generated or read from cache.
    Whenever a item is requested from object cache that is a partial miss
     (a miss from object cache but a hit from buffer cache), the item gets
     generated from buffer cache.
     In this case, and also if a new object item is added explicitly,
     a temporary reference to  the item is added, that expires after 20 seconds

    For cells, there is normally only one buffer cache item, because all expressions
     of the same cell._storage_type are mapped to it.
    In contrast, every expression typically has its own semantic checksum (reflecting
     both cell type and subpath), and therefore its own object cache item.
    """
    def __init__(self, manager):
        value_caches.add(self)
        self.manager = weakref.ref(manager) if manager is not None else lambda: None
        self._buffer_cache = {} #buffer-checksum-to-(refcount, refcount, value)
        self._object_cache = WeakValueDictionary() #semantic-key-to-value

        # TODO: caches for annotation purposes: reverse caches, ...

    def incref(self, buffer_checksum, buffer, *, has_auth):
        """Increase refcount for buffer checksum
        Add an extra non-auth refcount that expires after 20 secs (unless smaller than 100k).
        
        Returns True if the full buffer has been successfully inserted
        If buffer is not None, this is always the case
        If buffer is None:
            - If the checksum is unknown, a dummy item is inserted
              (returns False)
            - If a dummy item is found, it is incref'ed
              (returns False)
            - If a full item (with non-None buffer) is found, it is incref'ed
              (returns True)
        """
        #print("INCREF", buffer_checksum.hex(), buffer)        
        item = self._buffer_cache.get(buffer_checksum)        
        if item is None:            
            if has_auth:
                item = 1, 1, buffer
            else:
                item = 0, 2, buffer
        else:
            if item[2] is not None:
                buffer = item[2] # *should* be equal, 
                                # if buffer is not None, 
                                # and everyone is honest 
                                #   (i.e. checksum is not spoofed)
            if has_auth:
                item = item[0] + 1, item[1] + 1, buffer
            else:
                item = item[0], item[1] + 2, buffer
        success = (buffer is not None)                        
        mgr = self.manager()
        if mgr is not None:
            tempref = functools.partial(self.decref, buffer_checksum, has_auth=False)
            mgr.temprefmanager.add_ref(tempref, 20.0) 
        self._buffer_cache[buffer_checksum] = item        
        redis_sinks.set_value(buffer_checksum, buffer)

        return success

    def decref(self, buffer_checksum, *, has_auth):
        item = self._buffer_cache[buffer_checksum]
        refcount_auth, refcount_nauth, buffer = item
        if (buffer is None or len(buffer) <= NO_EXPIRE_SIZE_LIMIT):
            return
        if has_auth:
            assert refcount_auth > 0
            if refcount_auth == 1 and refcount_nauth == 0:
                self._buffer_cache.pop(buffer_checksum)
                return
            item = refcount_auth - 1, refcount_nauth, buffer
            self._buffer_cache[buffer_checksum] = item
        else:
            assert refcount_nauth > 0
            if refcount_auth == 0 and refcount_nauth == 1:
                self._buffer_cache.pop(buffer_checksum)
                return
            item = refcount_auth, refcount_nauth - 1, buffer
            self._buffer_cache[buffer_checksum] = item

    def add_semantic_key(self, semantic_key, value):
        assert isinstance(semantic_key, SemanticKey)        
        try:
            self._object_cache[semantic_key] = value
            hash(value)
        except TypeError:
            value = WeakrefableWrapper(value)
            self._object_cache[semantic_key] = value
        self.manager().temprefmanager.add_ref(value, 20.0)

    def get_object(self, semantic_key):
        assert isinstance(semantic_key, SemanticKey)
        item = self._object_cache.get(semantic_key)
        if isinstance(item, WeakrefableWrapper):
            return item.value
        else:
            return item

    def get_buffer(self, checksum):
        if checksum is None:
            return None
        item = self._buffer_cache.get(checksum)
        if item is None or item[2] is None:
            item = None
            value = redis_caches.get_value(checksum)
            if value is not None:
                item = 1, 1, value
        return item

    def value_check(self, checksum):
        """For the communionserver..."""
        if checksum in self._buffer_cache:
            return True
        assert checksum is not None
        return redis_caches.has_value(checksum)

"""
NOTE: value caches coming from expressionlevel>0 or from streams will never be
auto-removed if their cell value changes. Non-authoritative cells may be configured to expire,
but authoritative values will now always be kept. """
