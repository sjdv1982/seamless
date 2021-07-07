from copy import deepcopy
from seamless.core import context, transformer, cell
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
def tf(a):
    import time
    time.sleep(a)
    return a + 42
ctx.tf.code.cell().set(tf)
ctx.a = cell("int").set(1)
ctx.a.connect(ctx.tf.a)
ctx.tf.meta = {
    "calculation_time": "2s"
}
ctx.compute()

def transformer_update():
    # Adapted from tasks/transformer_update.py
    manager = ctx._get_manager()
    livegraph = manager.livegraph
    taskmanager = manager.taskmanager
    upstreams = livegraph.transformer_to_upstream[ctx.tf]

    inputpin_checksums = {}
    for pinname, accessor in upstreams.items():
        if pinname == "META" and accessor is None:
            continue
        inputpin_checksums[pinname] = accessor._checksum

    celltypes = {}
    for pinname, accessor in upstreams.items():
        if pinname == "META" and accessor is None:
            continue
        wa = accessor.write_accessor
        celltypes[pinname] = wa.celltype, wa.subcelltype
    cachemanager = manager.cachemanager
    outputname = ctx.tf._output_name
    outputpin0 = ctx.tf._pins[outputname]
    output_celltype = outputpin0.celltype
    output_subcelltype = outputpin0.subcelltype
    outputpin = outputname, output_celltype, output_subcelltype
    return celltypes, inputpin_checksums, outputpin

async def main():
    tf_cache = ctx._get_manager().cachemanager.transformation_cache
    celltypes,inputpin_checksums,outputpin = transformer_update()
    transformation, transformation_build_exception = await tf_cache.build_transformation(
        ctx.tf, celltypes,inputpin_checksums,outputpin
    )
    meta_checksum = transformation["__meta__"]
    meta = json.loads(buffer_cache.get_buffer(meta_checksum))
    print(meta)
    def calc_meta(a):
        return {
            "calculation_time": "{:d}s".format(a)
        }
    ctx.calc_meta = transformer({
        "a": {
            "io": "input",
            "celltype": "int",
        },
        "result": {
            "io": "output",
            "celltype": "plain",
        },

    })
    ctx.calc_meta.code.cell().set(calc_meta)
    ctx.a.connect(ctx.calc_meta.a)
    ctx.meta = cell("plain")
    ctx.calc_meta.result.connect(ctx.meta)
    await ctx.computation()
    print(ctx.meta.value)
    ctx.meta.connect(ctx.tf.META)
    await ctx.computation()
    celltypes,inputpin_checksums,outputpin = transformer_update()
    transformation, transformation_build_exception = await tf_cache.build_transformation(
        ctx.tf, celltypes,inputpin_checksums,outputpin
    )
    meta_checksum = transformation["__meta__"]
    meta = json.loads(buffer_cache.get_buffer(meta_checksum))
    print(meta)

    print("SET 4")
    ctx.a.set(4)
    await ctx.computation()
    print(ctx.meta.value)
    celltypes,inputpin_checksums,outputpin = transformer_update()
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