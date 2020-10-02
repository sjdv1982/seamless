import sys
import seamless
cache = seamless.database_cache
cache.connect()
checksum = bytes.fromhex(sys.argv[1])
key = "tfr-" + checksum.hex()
if cache.has_key(key):
    cache.delete_key(key)
    print("Transformation result deleted")
else:
    print("Transformation result not found")