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
            r.get("test")
            _redis_connections[key] = r
        else:
            r = _redis_connections[key]
        if r is None:
            raise redis.exceptions.ConnectionError
        self.connection = r
        _redis_sinks.append(self)
    
    def set_transformation_result(self, tf_checksum, checksum):
        r = self.connection
        key = b"tfr:" +  tf_checksum
        r.set(key, checksum)

    def sem2syn(self, sem_checksum, syn_checksums):        
        r = self.connection
        key = b"s2s:" +  sem_checksum
        for syn_checksum in syn_checksums:
            r.sadd(key, syn_checksum)

    def set_buffer(self, checksum, buffer):
        r = self.connection
        key = b"buf:" + checksum
        r.set(key, buffer)

    def set_buffer_length(self, checksum, length):
        r = self.connection
        key = b"bfl:" + checksum
        r.set(key, length)

    def add_small_buffer(self, checksum):
        r = self.connection
        key = b"smallbuffers"
        r.sadd(key, checksum)

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
            r.get("test")
            _redis_connections[key] = r
        else:
            r = _redis_connections[key]
        self.connection = r
        _redis_caches.append(self)

    def get_transformation_result(self, checksum):
        r = self.connection
        key = b"tfr:" + checksum
        return r.get(key)

    def sem2syn(self, sem_checksum):
        r = self.connection
        key = b"s2s:" +  sem_checksum
        members = r.smembers(key)
        return members

    def get_buffer(self, checksum):
        r = self.connection
        key = b"buf:" + checksum
        return r.get(key)

    def has_buffer(self, checksum):
        r = self.connection
        key = b"buf:" + checksum
        return r.exists(key)

    def get_buffer_length(checksum):
        # 1 for small buffers
        key = b"smallbuffers"
        if r.sismember(key, checksum):
            return 1
        key = b"bfl:" + checksum
        return r.get(key)

    def get_compile_result(self, checksum):
        r = self.connection
        key = b"cpl:" + checksum
        return r.get(key)        

class RedisSinks:
    @staticmethod
    def sinks():
        return _redis_sinks
    def sem2syn(self, sem_checksum, syn_checksums):
        assert isinstance(syn_checksums, list)
        if sem_checksum is None or not len(syn_checksums):
            return
        members = set()
        for redis_sink in _redis_sinks:
            redis_sink.sem2syn(
                sem_checksum, syn_checksums
            )
    def set_buffer(self, checksum, buffer):   
        if checksum is None or buffer is None:
            return     
        for redis_sink in _redis_sinks:
            redis_sink.set_buffer(checksum, buffer)
    def set_buffer_length(self, checksum, length):   
        if checksum is None:
            return     
        for redis_sink in _redis_sinks:
            redis_sink.set_buffer_length(checksum, length)
    def add_small_buffer(self, checksum):
        if checksum is None:
            return     
        for redis_sink in _redis_sinks:
            redis_sink.add_small_buffer(checksum)
    def set_transformation_result(self, tf_checksum, checksum):
        if tf_checksum is None or checksum is None:
            return        
        for redis_sink in _redis_sinks:
            redis_sink.set_transformation_result(tf_checksum, checksum)
    def set_compile_result(self, checksum, buffer):   
        if checksum is None or buffer is None:
            return     
        for redis_sink in _redis_sinks:
            redis_sink.set_compile_result(checksum, buffer)


class RedisCaches:
    def sem2syn(self, sem_checksum):
        if sem_checksum is None:
            return     
        members = set()
        for redis_cache in _redis_caches:
            curr_members = redis_cache.sem2syn(sem_checksum)            
            if curr_members is not None:
                members.update(curr_members)
        if len(members):
            return list(members)
    def get_transform_result(self, tf_checksum):
        for redis_cache in _redis_caches:
            checksum = redis_cache.get_transformation_result(tf_checksum)
            if checksum is not None:
                return checksum
    def get_buffer(self, checksum): 
        for redis_cache in _redis_caches:
            buffer = redis_cache.get_buffer(checksum)
            if buffer is not None:
                return buffer
    def get_buffer_length(self, checksum): 
        for redis_cache in _redis_caches:
            length = redis_cache.get_buffer_length(checksum)
            if length is not None:
                return length
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