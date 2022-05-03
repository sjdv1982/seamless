import seamless
seamless.database_cache.connect()
seamless.database_sink.connect()

from seamless.highlevel import Context
ctx = Context()
ctx.a = "testvalue"
ctx.compute()
cs = ctx.a.checksum

print(seamless.database_cache.get_buffer(cs))
print(seamless.database_cache.get_filename(cs))
seamless.database_cache.set_filezones(["local"])  # default zone 
print(seamless.database_cache.get_filename(cs))
seamless.database_cache.set_filezones(["whatever"])  # default zone 
print(seamless.database_cache.get_filename(cs))  # None

