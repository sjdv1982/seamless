"""
Trees are accessors where the cell pointer has been replaced by a buffer 
 checksum.
This means that a transformation in dict-of-expressions form is reproducible.
A expression can be evaluated (reading the buffer in storage mode, and 
 following the path) which leads to an object with a semantic checksum.

Applying the connection mode (transfer mode + access mode + content type,
 see protocol.py) to the objects finally leads 

Trees are fundamentally ephemeral and their caches are never stored, 
 other than in transformers.
"""

import weakref
import json
from collections import OrderedDict

class Expression:
    __slots__ = [
        "celltype",
        "storage_type",
        "buffer_checksum",
        "subpath", # optional
        "access_mode",
        "content_type",
        "source_access_mode", # optional
        "source_content_type", # optional
    ]
    def __init__(self):
        self.subpath = None
        self.source_access_mode = None
        self.source_content_type = None

    def __str__(self):
        d = OrderedDict()        
        for slot in self.__slots__:
            d[slot] = getattr(self, slot)
        d["buffer_checksum"] = self.buffer_checksum.hex()
        return json.dumps(d, indent=2)

    def __hash__(self):
        return hash(str(self))
    
class ExpressionCache:
    """Maintains expression caching
    
    Expression-to-semantic-key caches are maintained and never 
     automatically cleared.
     (TODO: keep time order of entries; upon memory limit, clear oldest ones)
     Semantic keys can be used to retrieve values from object cache,
      or to build level 2 transformations
     If there is no semantic key, it can be built by applying the expression
      to the buffer (which builds the object also)
    
    Trees normally don't keep their own buffer checksum, instead
     retrieving the buffer checksum that they contain.
    However, if a cell has cache expression depth > 0, a simplified expression is 
     constructed for each item (setting access type and semantic type to
     None)     
     and the buffer checksum of that item is computed and stored.
    """
    
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.expression_to_buffer_checksum = {} # only for expression depth > 0
        self.expression_to_semantic_key = {}


