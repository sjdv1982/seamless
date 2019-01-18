import weakref

class TransformCache:
    """Caches transformer results
    
    Transformers consist of three levels:
    - Level 0 - Graph transformer: dictionary of accessors
    - Level 1 - Outer transformation: a dictionary of trees
    - Level 2 - Inner transformation: a dictionary of semantic keys
      Each semantic key consists of a semantic checksum, an access mode, and a content type

    The manager commands the conversion of level 0 to level 1
    Level 1 is then checked against cache
    If it misses, level 2 is then built and checked against cache.
     This will put the values of the semantic checksums in object cache
      until a hit on the result checksum has been obtained
    If it misses, level 1 and level 2 are sent out to external cache
    If it misses, level 1 and level 2 are sent out to remote computation
    If this fails, computation is performed locally using level 2

    TODO (medium-term): if there is stream annotations, 
      level 1 is converted to a stream-of-level-2.
      Everything that has a cache hit is bypassed, everything that is to be
      performed locally is sent into the stream execution code
    TODO (long-term): Accessors may point to actual stream objects, with an API.
     In this way, streams can be connected to each other as they grow, 
     reducing latency.
     This affects the level1-to-level2 transformation, as there is no longer
      a checksum available before computation commences.

    Level 0 and level 2 are explicitly stored. Level 1 is always easily regenerated from level 0
    """
    def __init__(self, manager):
        self.manager = weakref.ref(manager)
        self.transformer_to_level0 = {} #id-to-checksum
        self.level1_to_level2 = {} #checksum-to-checksum
        self.value_level0 = {} # checksum-to-(value,nref), like ValueCache; value is a dict-of-accessor-checksums
        self.value_level2 = {} # checksum-to-(value,nref), like ValueCache; value is a dict-of-semantic-keys

        # TODO: caches for annotation purposes: value_level1, reverse caches, ...