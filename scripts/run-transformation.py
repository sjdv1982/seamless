import sys
checksum = sys.argv[1]
checksum = bytes.fromhex(checksum)
if len(sys.argv) > 2 and sys.argv[2] == "--direct-print":
    import seamless.core.execute
    seamless.core.execute.DIRECT_PRINT = True

import seamless
seamless.database_sink.connect()
seamless.database_cache.connect()

result = seamless.run_transformation(checksum)
if result is not None:
    result = result.hex()
print(result)