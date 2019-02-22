import json
import weakref
import functools
import traceback
import asyncio
from .expression_cache import Expression
from .value_cache import SemanticKey
from ...get_hash import get_hash

from .redis_client import redis_sinks, redis_caches

class TransformerLevel1:
    def __init__(self, expressions, output_name):
        self._expressions = expressions
        self.output_name = output_name
        a = []
        for key in sorted(expressions.keys()):            
            assert isinstance(key, str)
            value = expressions[key]
            assert isinstance(value, Expression)
            a.append((key, str(value)))
        a.append(output_name)
        self._frozen_expressions = tuple(a)        
        self._hash = get_hash(self.serialize()).hex()
    
    def __hash__(self):
        return hash(self._frozen_expressions)

    def __iter__(self):
        return iter(self._expressions)

    def __getitem__(self, key):
        return self._expressions[key]

    def serialize(self):
        return json.dumps(self._frozen_expressions)+"\n"

    @classmethod
    def deserialize(cls, stream):
        frozen_expressions = json.loads(stream)
        expressions0, output_name = frozen_expressions[:-1], frozen_expressions[-1]
        expressions = {}
        for key, expr in expressions0:
            expr = json.loads(expr)
            expr["buffer_checksum"] = bytes.fromhex(expr["buffer_checksum"])
            expression = Expression()
            for k,v in expr.items():
                setattr(expression, k, v)
            expressions[key] = expression
        return cls(expressions, output_name)

    def get_hash(self):    
        return self._hash


class TransformerLevel2:
    def __init__(self, semantic_keys, output_name):
        self._semantic_keys = semantic_keys
        self.output_name = output_name
        a = []
        for key in sorted(semantic_keys.keys()):
            assert isinstance(key, str)
            value = semantic_keys[key]
            assert isinstance(value, SemanticKey)
            v = (
                value.semantic_checksum.hex(), 
                value.access_mode,
                value.content_type,
                value.subpath
            )
            v = json.dumps(v)
            a.append(get_hash(v+"\n").hex())
        a.append(output_name)
        self._frozen_semantic_keys = tuple(a)
        aa = json.dumps(a)
        self._hash = get_hash(aa+"\n").hex()
    
    def __hash__(self):
        return hash(self._frozen_semantic_keys)

    def __iter__(self):
        return iter(self._semantic_keys)

    def __getitem__(self, key):
        return self._semantic_keys[key]

    def get_hash(self):    
        return self._hash

transform_caches = weakref.WeakSet()  

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
        transform_caches.add(self)
        self.manager = weakref.ref(manager)        
        self.transformer_to_level0 = {} #id-to-dict-of-accessors
        self.transformer_to_level1 = {} #id-to-TransformerLevel1
        self.transformer_to_cells = {}
        self.hlevel1_to_level2 = {}
        self.transformer_from_hlevel1 = {}  # This relation is not unique, but we need only one
        self.hlevel1_from_hlevel2 = {}  # This relation is not unique, but we need only one
        self.refcount_hlevel1 = {} 
        self.refcount_hlevel2 = {}
        self.revhash_hlevel1 = {}
        self.result_hlevel1 = {} #HASH-of-level1 to result-checksum (buffer)
        self.result_hlevel2 = {} #HASH-level2 to result-checksum (buffer)

        # TODO: caches for annotation purposes: reverse caches, ...

    def incref(self, level1):
        hlevel1 = level1.get_hash()
        refcount = self.refcount_hlevel1.pop(hlevel1, 0)
        self.refcount_hlevel1[hlevel1] = refcount + 1
        self.revhash_hlevel1[hlevel1] = level1

    def decref(self, level1):
        hlevel1 = level1.get_hash()
        refcount = self.refcount_hlevel1.pop(hlevel1)
        if refcount > 1:
            self.refcount_hlevel1[hlevel1] = refcount - 1
            return
        self.transformer_from_hlevel1.pop(hlevel1)
        ###self.result_hlevel1.pop(hlevel1, None)  # for now, hold on to this forever
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
        if curr_level1 is not None and curr_level1.get_hash() in self.refcount_hlevel1:
            callback = functools.partial(self.decref, curr_level1)
            self.manager().temprefmanager.add_ref(callback, 20.0)
        self.transformer_to_level1[transformer] = level1
        hlevel1 = level1.get_hash()
        #if hlevel1 not in self.transformer_from_hlevel1:
        self.transformer_from_hlevel1[hlevel1] = transformer
        self.incref(level1)
        

    def _decref_level2(self, level2):
        # Does not decref corresponding level1
        hlevel2 = level2.get_hash()
        refcount = self.refcount_hlevel2.pop(hlevel2)
        if refcount > 1:
            self.refcount_hlevel2[hlevel2] = refcount - 1
            return
        ###self.result_hlevel2.pop(hlevel2, None) # for now, hold on to this forever
        self.hlevel1_from_hlevel2.pop(hlevel2)

    def _incref_level2(self, level2):
        hlevel2 = level2.get_hash()
        refcount = self.refcount_hlevel2.pop(hlevel2, 0)
        self.refcount_hlevel2[hlevel2] = refcount + 1        

    async def build_level2(self, level1):
        if not isinstance(level1, TransformerLevel1):
            raise TypeError(level1)

        manager = self.manager()
        vcache = manager.value_cache
        hlevel1 = level1.get_hash()
        result = self.hlevel1_to_level2.get(hlevel1)
        if result is not None:
            return result
        semantic_keys = {}
        tasks = []
        pinnames = list(level1)
        for pin in pinnames:
            expression = level1[pin]
            checksum = expression.buffer_checksum
            task = manager.get_value_from_checksum_async(checksum)
            tasks.append(task)        
        results = await asyncio.gather(*tasks)
        for pinnr, pin in enumerate(pinnames):
            expression = level1[pin]
            buffer_item = results[pinnr]
            if buffer_item is None:
                raise ValueError("Checksum not in value cache") 
            _, _, buffer = buffer_item
            _, semantic_key = manager.cache_expression(expression, buffer)
            semantic_keys[pin] = semantic_key

        result = TransformerLevel2(semantic_keys, level1.output_name)
        return result


    def set_level2(self, level1, level2):
        hlevel1 = level1.get_hash()
        old_level2 = self.hlevel1_to_level2.get(hlevel1)
        if old_level2 is not None:
            assert hash(old_level2) == hash(level2)
            return
        self.hlevel1_to_level2[hlevel1] = level2
        hlevel2 = level2.get_hash()
        if hlevel2 not in self.hlevel1_from_hlevel2:
            self.hlevel1_from_hlevel2[hlevel2] = hlevel1
        self._incref_level2(level2)


    def get_result(self, hlevel1):
        result = self.result_hlevel1.get(hlevel1)
        if result is not None:
            return result
        return redis_caches.get_transform_result(bytes.fromhex(hlevel1))

    def set_result(self, hlevel1, checksum):
        self.result_hlevel1[hlevel1] = checksum
        redis_sinks.set_transform_result(bytes.fromhex(hlevel1), checksum)       

    def set_result_level2(self, hlevel2, checksum):
        self.result_hlevel2[hlevel2] = checksum
        redis_sinks.set_transform_result_level2(bytes.fromhex(hlevel2), checksum)