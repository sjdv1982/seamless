import weakref
import functools
from .expression_cache import Expression
from .value_cache import SemanticKey

class TransformerLevel1:
    def __init__(self, expressions):
        self._expressions = expressions
        a = []
        for key in sorted(expressions.keys()):
            assert isinstance(key, str)
            value = expressions[key]
            assert isinstance(value, Expression)
            a.append(hash(value))
        self._frozen_expressions = tuple(a)
    
    def __hash__(self):
        return hash(self._frozen_expressions)

    def __getattr__(self, key):
        return self._expressions[key]

class TransformerLevel2:
    def __init__(self, semantic_keys):
        self._semantic_keys = semantic_keys
        a = []
        for key in sorted(semantic_keys.keys()):
            assert isinstance(key, str)
            value = semantic_keys[key]
            assert isinstance(value, SemanticKey)
            a.append(hash(value))
        self._frozen_semantic_keys = tuple(a)
    
    def __hash__(self):
        return hash(self._frozen_semantic_keys)

    def __getattr__(self, key):
        return self._semantic_keys[key]

  
class TransformCache:
    """Caches transformer results

    Transformers consist of three levels:
    - Level 0 - Graph transformer: dictionary of accessors
    - Level 1 - Outer transformation: a dictionary of expressions
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
    """
    def __init__(self, manager):
        self.manager = weakref.ref(manager)        
        self.transformer_to_level0 = {} #id-to-dict-of-accessors
        self.transformer_to_level1 = {} #id-to-TransformerLevel1
        self.transformer_to_cells = {}
        self.level1_to_level2 = {}  
        self.refcount_level1 = {}
        self.result_level1 = {} #level1-to-result-checksum (buffer)
        self.result_level2 = {} #level2-to-result-checksum (buffer)

        # TODO: caches for annotation purposes: reverse caches, ...

    def incref(self, level1):
        refcount = self.refcount_level1.pop(level1, 0)
        self.refcount_level1[level1] = refcount + 1

    def decref(self, level1):
        refcount = self.refcount_level1.pop(level1)
        if refcount > 1:
            self.refcount_level1[level1] = refcount - 1
            return
        self.result_level1.pop(level1, None)
        level2 = self.level1_to_level2.pop(level1, None)
        if level2 is not None:
            self.result_level2.pop(level2)

    def build_expressions(self, transformer):
        manager = self.manager()
        accessors = self.transformer_to_level0[transformer]
        expressions = {}
        for pin, accessor in accessors.items():
            expression = manager.build_expression(accessor)
            expressions[pin] = expression
        level1 = TransformerLevel1(expressions)
        curr_level1 = self.transformer_to_level1.get(transformer)
        if curr_level1 == level1:
            return
        if curr_level1 is not None and curr_level1 in self.refcount_level1:
            callback = functools.partial(self.decref, curr_level1)
            self.manager().temprefmanager.add_ref(callback, 20.0)
        self.transformer_to_level1[transformer] = level1
        self.incref(level1)
        
