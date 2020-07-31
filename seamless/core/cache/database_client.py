import asyncio

class DatabaseSink:
    # TODO: has_key
    def connect(self, *, host='localhost',port=6379,
      store_compile_result=True
    ):
        raise NotImplementedError
        import redis
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
        key = "tfr:" +  tf_checksum.hex()
        r.set(key, checksum)

    def sem2syn(self, semkey, syn_checksums):
        r = self.connection
        sem_checksum, celltype, subcelltype = semkey
        key = "s2s:{},{},{}".format(sem_checksum.hex(), celltype, subcelltype)
        for syn_checksum in syn_checksums:
            r.sadd(key, syn_checksum)

    def set_buffer(self, checksum, buffer):
        r = self.connection
        key = "buf:" + checksum.hex()
        r.set(key, buffer)

    def set_buffer_length(self, checksum, length):
        r = self.connection
        key = "bfl:" + checksum.hex()
        r.set(key, length)

    def add_small_buffer(self, checksum):
        r = self.connection
        key = "smallbuffers"
        r.sadd(key, checksum)

    def set_compile_result(self, checksum, buffer):
        if not self.store_compile_result:
            return
        r = self.connection
        key = "cpl:" + checksum.hex()
        r.set(key, buffer)

class DatabaseCache:
    # TODO: has_key
    def connect(self, *, host='localhost',port=6379):
        raise NotImplementedError
        import redis
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
        key = "tfr:" + checksum.hex()
        return r.get(key)

    def sem2syn(self, semkey):
        r = self.connection
        sem_checksum, celltype, subcelltype = semkey
        key = "s2s:{},{},{}".format(sem_checksum.hex(), celltype, subcelltype)
        members = r.smembers(key)
        return members

    def get_buffer(self, checksum):
        r = self.connection
        key = "buf:" + checksum.hex()
        return r.get(key)

    def has_buffer(self, checksum):
        r = self.connection
        key = "buf:" + checksum.hex()
        return r.exists(key)

    def get_buffer_length(self, checksum):
        # 1 for small buffers
        r = self.connection
        key = "smallbuffers"
        if r.sismember(key, checksum):
            return 1
        key = "bfl:" + checksum.hex()
        return r.get(key)

    def get_compile_result(self, checksum):
        r = self.connection
        key = "cpl:" + checksum.hex()
        return r.get(key)


database_sink = DatabaseSink()
database_cache = DatabaseCache()