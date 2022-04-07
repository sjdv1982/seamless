import sys
import seamless
cache = seamless.database_cache
cache.connect()
checksum = bytes.fromhex(sys.argv[1])
deleted = cache.delete_key("transformation", checksum)
if deleted:
    print("Transformation result deleted")
else:
    print("Transformation result not found")