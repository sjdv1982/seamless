import argparse
parser = argparse.ArgumentParser()
parser.add_argument("checksum")
parser.add_argument("--direct-print", dest="direct_print", action="store_true")
parser.add_argument("--filezone", action="append")
args = parser.parse_args()
checksum = args.checksum
checksum = bytes.fromhex(checksum)
if args.direct_print:
    import seamless.core.execute
    seamless.core.execute.DIRECT_PRINT = True

import seamless
seamless.database_sink.connect()
seamless.database_cache.connect()
if args.filezone:
    seamless.database_cache.set_filezones(args.filezone)

result = seamless.run_transformation(checksum)
if result is not None:
    result = result.hex()
print(result)