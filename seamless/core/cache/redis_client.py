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
    
    def set_transformation_result(self, tf_checksum, checksum):
        r = self.connection
        key = b"tfr:" +  tf_checksum
        r.set(key, checksum)

    def set_buffer(self, checksum, buffer):
        r = self.connection
        key = b"buf:" + checksum
        r.set(key, buffer)

    def set_compile_result(self, checksum, buffer):
        if not self.store_compile_result:
            return
        r = self.connection
        key = b"cpl:" + checksum
        r.set(key, buffer)

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

    def get_transformation_result(self, checksum):
        r = self.connection
        key = b"tfr:" + checksum
        return r.get(key)

    def get_buffer(self, checksum):
        r = self.connection
        key = b"buf:" + checksum
        return r.get(key)

    def has_buffer(self, checksum):
        r = self.connection
        key = b"buf:" + checksum
        return r.exists(key)

    def get_compile_result(self, checksum):
        r = self.connection
        key = b"cpl:" + checksum
        return r.get(key)        

class RedisSinks:
    @staticmethod
    def sinks():
        return _redis_sinks
    def set_buffer(self, checksum, buffer):   
        if checksum is None or buffer is None:
            return     
        for redis_sink in _redis_sinks:
            redis_sink.set_buffer(checksum, buffer)
    def set_transform_result(self, tf_checksum, checksum):
        if tf_checksum is None or checksum is None:
            return        
        for redis_sink in _redis_sinks:
            redis_sink.set_transform_result(tf_checksum, checksum)
    def set_compile_result(self, checksum, buffer):   
        if checksum is None or buffer is None:
            return     
        for redis_sink in _redis_sinks:
            redis_sink.set_compile_result(checksum, buffer)


class RedisCaches:
    def get_transform_result(self, tf_checksum):
        for redis_cache in _redis_caches:
            checksum = redis_cache.get_transform_result(tf_checksum)
            if checksum is not None:
                return checksum
    def get_buffer(self, checksum): 
        for redis_cache in _redis_caches:
            buffer = redis_cache.get_buffer(checksum)
            if buffer is not None:
                return buffer
    def has_buffer(self, checksum):        
        for redis_cache in _redis_caches:
            buffer = redis_cache.has_buffer(checksum)
            if buffer:
                return True
        return False
    def get_compile_result(self, checksum): 
        for redis_cache in _redis_caches:
            buffer = redis_cache.get_compile_result(checksum)
            if buffer is not None:
                return buffer

redis_sinks = RedisSinks()
redis_caches = RedisCaches()