# WIP tool to re-evaluate structured cell joins with run-transformation
import json
import sys
import seamless
from seamless.highlevel import Checksum
from seamless.core.cache.buffer_cache import buffer_cache
from seamless import calculate_dict_checksum
seamless.delegate(level=1)

join_dict_checksum = Checksum(sys.argv[1])
join_dict_buffer = buffer_cache.get_buffer(join_dict_checksum.bytes())
if join_dict_buffer is None:
    print(f"Cannot retrieve buffer for supplied join dict checksum {join_dict_checksum}", file=sys.stderr)
    exit(0)
join_dict = json.loads(join_dict_buffer.decode())
assert isinstance(join_dict, dict)

transformation_dict = {
    "__language__": "<structured_cell_join>",
    "structured_cell_join": join_dict
}
print(json.dumps(transformation_dict, sort_keys=True, indent=2))
print(calculate_dict_checksum(transformation_dict, hex=True))

if len(sys.argv) > 2:
    from seamless.core.protocol.json import json_dumps
    content = json_dumps(transformation_dict, as_bytes=True) + b"\n"
    with open(sys.argv[2], "wb") as f:
        f.write(content)
    

