import redis

class RedisSink:
    """
    RedisSink can be in cache mode or not
    If in cache mode, you should set eviction policy to allkeys-lru or allkeys-lfu
    In non-cache mode, you should set eviction policy to volatile-ttl
      Seamless will set extremely long (30 years) expiry times for non-authoritative buffers
      The higher the importance, the higher the expiry time
      Thus, the least important buffers get evicted first
    """
    def __init__(self, connection, config):
        self.cache = True if config.get("cache") else False
        self.connection = connection

    @property
    def id(self):
        return id(self.connection)

    async def set(self, key, value, authoritative=True, importance=None):
        if isinstance(key, bytes):
            key = key.decode()
        assert isinstance(value, bytes)
        r = self.connection
        if self.cache and not authoritative:
            expiry = int(1e9 + 1000 * importance) # in seconds
            r.set(key, value, ex=expiry)
        else:
            r.set(key, value)

    async def rename(self, key1, key2):
        """Renames a buffer, assumes that key2 is authoritative"""
        if isinstance(key2, bytes):
            key1 = key1.decode()
        if isinstance(key2, bytes):
            key2 = key2.decode()
        r = self.connection
        try:
            r.rename(key1, key2)
        except:
            value = r.get(key1)
            r.set(key2, value)
            r.delete(key1)

    async def delete_key(self, key):
        if isinstance(key, bytes):
            key = key.decode()
        r = self.connection
        r.delete(key)

    async def has_key(self, key):
        if isinstance(key, bytes):
            key = key.decode()
        r = self.connection
        return r.exists(key)

    async def add_sem2syn(self, key, syn_checksums):
        if isinstance(key, bytes):
            key = key.decode()
        r = self.connection
        for syn_checksum in syn_checksums:
            assert isinstance(syn_checksum, bytes)
            r.sadd(key, syn_checksum)


class RedisSource:
    def __init__(self, connection, config):
        self.connection = connection

    @property
    def id(self):
        return id(self.connection)

    async def get(self, key):
        if isinstance(key, bytes):
            key = key.decode()
        r = self.connection
        return r.get(key)

    async def delete_key(self, key):
        if isinstance(key, bytes):
            key = key.decode()
        r = self.connection
        r.delete(key)

    async def has_key(self, key):
        if isinstance(key, bytes):
            key = key.decode()
        r = self.connection
        return r.exists(key)

    async def get_sem2syn(self, key):
        if isinstance(key, bytes):
            key = key.decode()
        r = self.connection
        members = r.smembers(key)
        return members

_connections = {}

def _get_connection(host, port):
    key = host, port
    if key not in _connections:
        r = redis.Redis(host=host, port=port, db=0)
        r.get("test")
        if r is None:
            raise redis.exceptions.ConnectionError
        _connections[key] = r
    return _connections[key]

def get_source(config):
    host = config["host"]
    port = config["port"]
    connection = _get_connection(host, port)
    return RedisSource(connection, config)

def get_sink(config):
    host = config["host"]
    port = config["port"]
    connection = _get_connection(host, port)
    return RedisSink(connection, config)