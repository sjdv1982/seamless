from seamless.core import context, transformer
from seamless.core.cache.buffer_cache import buffer_cache
import json
ctx = context(toplevel=True)
ctx.tf = transformer({
    "a": {
        "io": "input",
        "celltype": "int",
    },
    "result": {
        "io": "output",
        "celltype": "int",
    },

})
ctx.tf.code.cell().set("a + 42")
ctx.tf.a.cell().set(1)
ctx.tf.meta = {
    "calculation_time": "1s"
}
ctx.compute()

# Adapted from tasks/transformer_update.py
manager = ctx._get_manager()
livegraph = manager.livegraph
taskmanager = manager.taskmanager
upstreams = livegraph.transformer_to_upstream[ctx.tf]

inputpin_checksums = {}
for pinname, accessor in upstreams.items():
    inputpin_checksums[pinname] = accessor._checksum

celltypes = {}
for pinname, accessor in upstreams.items():
    wa = accessor.write_accessor
    celltypes[pinname] = wa.celltype, wa.subcelltype
cachemanager = manager.cachemanager
transformation_cache = cachemanager.transformation_cache
outputname = ctx.tf._output_name
outputpin0 = ctx.tf._pins[outputname]
output_celltype = outputpin0.celltype
output_subcelltype = outputpin0.subcelltype
outputpin = outputname, output_celltype, output_subcelltype

tf_cache = ctx._get_manager().cachemanager.transformation_cache
async def main():
    transformation, transformation_build_exception = await tf_cache.build_transformation(
        ctx.tf, celltypes,inputpin_checksums,outputpin
    )
    meta_checksum = transformation["__meta__"]
    meta = json.loads(buffer_cache.get_buffer(meta_checksum))
    print(meta)

import asyncio
asyncio.get_event_loop().run_until_complete(
    main()
)    