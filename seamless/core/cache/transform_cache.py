import weakref
import functools
from .expression_cache import Expression
from .value_cache import SemanticKey

class TransformerLevel1:
    def __init__(self, expressions, output_name):
        self._expressions = expressions
        self.output_name = output_name
        a = []
        for key in sorted(expressions.keys()):
            assert isinstance(key, str)
            value = expressions[key]
            assert isinstance(value, Expression)
            a.append(hash(value))
        a.append(hash(output_name))
        self._frozen_expressions = tuple(a)
    
    def __hash__(self):
        return hash(self._frozen_expressions)

    def __iter__(self):
        return iter(self._expressions)

    def __getitem__(self, key):
        return self._expressions[key]

class TransformerLevel2:
    def __init__(self, semantic_keys, output_name):
        self._semantic_keys = semantic_keys
        self.output_name = output_name
        a = []
        for key in sorted(semantic_keys.keys()):
            assert isinstance(key, str)
            value = semantic_keys[key]
            assert isinstance(value, SemanticKey)
            a.append(hash(value))
        a.append(hash(output_name))
        self._frozen_semantic_keys = tuple(a)
    
    def __hash__(self):
        return hash(self._frozen_semantic_keys)

    def __iter__(self):
        return iter(self._semantic_keys)

    def __getitem__(self, key):
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
        self.hlevel1_to_level2 = {}
        self.transformer_from_hlevel1 = {}  # This relation is not unique, but we need only one
        self.hlevel2_from_hlevel1 = {}  # This relation is not unique, but we need only one
        self.refcount_hlevel1 = {} 
        self.refcount_hlevel2 = {}
        self.revhash_hlevel1 = {}
        self.result_hlevel1 = {} #HASH-of-level1 to result-checksum (buffer)
        self.result_hlevel2 = {} #HASH-level2 to result-checksum (buffer)

        # TODO: caches for annotation purposes: reverse caches, ...

    def incref(self, level1):
        hlevel1 = hash(level1)
        refcount = self.refcount_hlevel1.pop(hlevel1, 0)
        self.refcount_hlevel1[hlevel1] = refcount + 1
        self.revhash_hlevel1[hlevel1] = level1

    def decref(self, level1):
        hlevel1 = hash(level1)
        refcount = self.refcount_hlevel1.pop(hlevel1)
        if refcount > 1:
            self.refcount_hlevel1[hlevel1] = refcount - 1
            return
        self.transformer_from_hlevel1.pop(hlevel1)
        self.result_hlevel1.pop(hlevel1, None)        
        level2 = self.hlevel1_to_level2.pop(hlevel1, None)        
        if level2 is not None:
            self._decref_level2(level2)

    def build_level1(self, transformer):
        #print("BUILD LEVEL1", transformer)
        manager = self.manager()
        accessors = self.transformer_to_level0[transformer]
        expressions = {}
        for pin, accessor in accessors.items():
            expression = manager.build_expression(accessor)
            expressions[pin] = expression
        level1 = TransformerLevel1(expressions, transformer._output_name)
        return level1
    
    def set_level1(self, transformer, level1):
        #print("SET LEVEL1", hash(level1))
        curr_level1 = self.transformer_to_level1.get(transformer)
        if curr_level1 == level1:
            return
        if curr_level1 is not None and hash(curr_level1) in self.refcount_hlevel1:
            callback = functools.partial(self.decref, curr_level1)
            self.manager().temprefmanager.add_ref(callback, 20.0)
        self.transformer_to_level1[transformer] = level1
        hlevel1 = hash(level1)
        if hlevel1 not in self.transformer_from_hlevel1:
            self.transformer_from_hlevel1[hlevel1] = transformer
        self.incref(level1)
        

    def _decref_level2(self, level2):
        # Does not decref corresponding level1
        hlevel2 = hash(level2)
        refcount = self.refcount_hlevel2.pop(hlevel2)
        if refcount > 1:
            self.refcount_hlevel2[hlevel2] = refcount - 1
            return
        self.result_hlevel2.pop(hlevel2, None)
        self.hlevel2_from_hlevel1.pop(hlevel2)

    def _incref_level2(self, level2):
        hlevel2 = hash(level2)
        refcount = self.refcount_hlevel2.pop(hlevel2, 0)
        self.refcount_hlevel2[hlevel2] = refcount + 1        

    def build_level2(self, level1):
        """Does not update any caches"""
        if not isinstance(level1, TransformerLevel1):
            raise TypeError(level1)

        manager = self.manager()
        vcache = manager.value_cache
        hlevel1 = hash(level1)
        result = self.hlevel1_to_level2.get(hlevel1)
        if result is not None:
            return result
        semantic_keys = {}
        for pin in level1:
            expression = level1[pin]
            checksum = expression.buffer_checksum
            buffer_item = vcache.get_buffer(checksum)
            if buffer_item is None:
                raise ValueError("Checksum not in value cache") 
            _, _, buffer = buffer_item
            _, semantic_key = manager.cache_expression(expression, buffer)
            semantic_keys[pin] = semantic_key
        result = TransformerLevel2(semantic_keys, level1.output_name)
        return result


    def set_level2(self, level1, level2):
        hlevel1 = hash(level1)
        old_level2 = self.hlevel1_to_level2.get(hlevel1)
        if old_level2 is not None:
            assert hash(old_level2) == hash(level2)
            return
        self.hlevel1_to_level2[hlevel1] = level2
        hlevel2 = hash(level2)
        if hlevel2 not in self.hlevel2_from_hlevel1:
            self.hlevel2_from_hlevel1[hlevel2] = hlevel1
        self._incref_level2(level2)
