"""
Trees are accessors where the cell pointer has been replaced by a buffer 
 checksum.
This means that a transformation in dict-of-trees form is reproducible.
A tree can be evaluated (reading the buffer in storage mode, and 
 following the path) which leads to an object with a semantic checksum.

Applying the connection mode (transfer mode + access mode + content type,
 see protocol.py) to the objects finally leads 

Trees are fundamentally ephemeral and their caches are never stored, 
 other than in transformers.
"""

import weakref

class Tree:
    __slots__ = [
        "cell_type",
        "storage_type",
        "cell_buffer_checksum",
        "subpath",
        "source_access_type", # optional
        "source_content_type" # optional
        "target_access_type", # optional
        "target_content_type" # optional
    ]
    def __init__(self):
        self.source_access_type = None
        self.source_content_type = None
        self.target_access_type = None
        self.target_content_type = None
    
class TreeCache:
    """Maintains tree caching
    
    Tree-to-semantic-key caches are maintained and never 
     automatically cleared.
     Semantic keys can be used to retrieve values from object cache,
      or to build level 2 transformations
     If there is no semantic key, it can be built by applying the tree
      to the buffer (which builds the object also)
    
    Trees normally don't keep their own buffer checksum, instead
     retrieving the buffer checksum that they contain.
    However, if a cell has cache tree depth > 0, a simplified tree is 
     constructed for each item (setting access type and semantic type to
     None)     
     and the buffer checksum of that item is computed and stored.
    """
    
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.tree_to_buffer_checksum = {} # only for tree depth > 0
        self.tree_to_semantic_key = {}


