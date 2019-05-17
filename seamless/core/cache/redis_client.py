import redis
import asyncio

_redis_connections = {}
_redis_sinks = []
_redis_caches = []

class RedisSink:
    def __init__(self, *, host='localhost',port=6379, 
      store_compile_result=True
    ):
        self.host = host
        self.port = port    
        self.store_compile_result = store_compile_result
        key = (host, port)
        if key not in _redis_connections:
            r = redis.Redis(host=host, port=port, db=0)
            _redis_connections[key] = r
        else:
            r = _redis_connections[key]
        self.connection = r
        _redis_sinks.append(self)
    
    def set_label(self, label, checksum):
        r = self.connection
        key = b"label:" + label.encode()
        r.set(key, checksum)

    def set_transform_result(self, hlevel1, checksum):
        r = self.connection
        key = b"tfresult:" + hlevel1
        r.set(key, checksum)

    def set_transform_result_level2(self, hlevel2, checksum):
        r = self.connection
        key = b"tfresult2:" + hlevel2
        r.set(key, checksum)

    def set_value(self, checksum, value):
        r = self.connection
        key = b"value:" + checksum
        r.set(key, value)

    def set_compile_result(self, checksum, value):
        if not self.store_compile_result:
            return
        r = self.connection
        key = b"compiled:" + checksum
        r.set(key, value)

class RedisCache:
    def __init__(self, *, host='localhost',port=6379):
        self.host = host
        self.port = port    
        key = (host, port)
        if key not in _redis_connections:
            r = redis.Redis(host=host, port=port, db=0)
            _redis_connections[key] = r
        else:
            r = _redis_connections[key]
        self.connection = r
        _redis_caches.append(self)

    def get_label(self, label):
        r = self.connection
        key = b"label:" + label.encode()
        return r.get(key)

    def get_transform_result(self, checksum):
        r = self.connection
        key = b"tfresult:" + checksum
        return r.get(key)


    def get_transform_result_level2(self, checksum):
        r = self.connection
        key = b"tfresult2:" + checksum
        return r.get(key)

    def get_value(self, checksum):
        r = self.connection
        key = b"value:" + checksum
        return r.get(key)

    def has_value(self, checksum):
        r = self.connection
        key = b"value:" + checksum
        return r.exists(key)

    def get_compile_result(self, checksum):
        r = self.connection
        key = b"compiled:" + checksum
        return r.get(key)        

class RedisSinks:
    @staticmethod
    def sinks():
        return _redis_sinks
    def set_value(self, checksum, value):   
        if checksum is None or value is None:
            return     
        for redis_sink in _redis_sinks:
            redis_sink.set_value(checksum, value)
    def set_label(self, checksum, label):    
        if checksum is None or label is None:
            return    
        for redis_sink in _redis_sinks:
            redis_sink.set_label(checksum, label)
    def set_transform_result(self, hlevel1, checksum):
        if hlevel1 is None or checksum is None:
            return        
        for redis_sink in _redis_sinks:
            redis_sink.set_transform_result(hlevel1, checksum)
    def set_transform_result_level2(self, hlevel2, checksum):
        if hlevel2 is None or checksum is None:
            return        
        for redis_sink in _redis_sinks:
            redis_sink.set_transform_result_level2(hlevel2, checksum)
    def set_compile_result(self, checksum, value):   
        if checksum is None or value is None:
            return     
        for redis_sink in _redis_sinks:
            redis_sink.set_compile_result(checksum, value)


class RedisCaches:
    def get_label(self, label):        
        for redis_cache in _redis_caches:
            value = redis_cache.get_label(label)
            if value is not None:
                return value
    def get_transform_result(self, hlevel1):
        for redis_cache in _redis_caches:
            value = redis_cache.get_transform_result(hlevel1)
            if value is not None:
                return value
    def get_transform_result_level2(self, hlevel2):
        for redis_cache in _redis_caches:
            value = redis_cache.get_transform_result_level2(hlevel2)
            if value is not None:
                return value
    def get_value(self, checksum): 
        for redis_cache in _redis_caches:
            value = redis_cache.get_value(checksum)
            if value is not None:
                return value
    def has_value(self, checksum):        
        for redis_cache in _redis_caches:
            value = redis_cache.has_value(checksum)
            if value:
                return True
        return False
    def get_compile_result(self, checksum): 
        for redis_cache in _redis_caches:
            value = redis_cache.get_compile_result(checksum)
            if value is not None:
                return value

redis_sinks = RedisSinks()
redis_caches = RedisCaches()