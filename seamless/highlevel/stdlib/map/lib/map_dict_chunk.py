def map_dict_chunk(ctx, chunksize, graph, inp, keyorder, has_uniform, elision, lib_module_dict):
    #print("map_dict_chunk", inp)
    from seamless.core import Cell as CoreCell
    from seamless.core import cell, context, macro, path, transformer
    from seamless.core.structured_cell import StructuredCell
    from seamless.core.HighLevelContext import HighLevelContext
    from seamless.core.unbound_context import UnboundContext
    import math

    pseudo_connections = []
    ctx.sc_data = cell("mixed")
    ctx.sc_buffer = cell("mixed")
    inpkeys = keyorder
    nchunks = math.ceil(len(inpkeys)/chunksize)
    ctx.sc = StructuredCell(
        data=ctx.sc_data,
        buffer=ctx.sc_buffer,
        inchannels=[(n+1,) for n in range(nchunks)],
        outchannels=[()],
        validate_inchannels=False
    )

    if has_uniform:
        ctx.uniform = cell("mixed")

    first = True
    for n in range(nchunks):
        pos = chunksize * n
        hc = HighLevelContext(graph)

        subctx = "subctx_" + str(n+1)
        setattr(ctx, subctx, hc)

        if first:
            if not hasattr(hc, "inp"):
                raise TypeError("map_dict_chunk context must have a cell called 'inp'")
        hci = hc.inp

        if has_uniform:
            if first :
                if not hasattr(hc, "uniform"):
                    raise TypeError("map_dict_chunk context must have a cell called 'uniform'")
                if isinstance(hc.uniform, StructuredCell):
                    raise TypeError("map_dict_chunk context has a cell called 'uniform', but its celltype must be mixed, not structured")
                if not isinstance(hc.uniform, CoreCell):
                    raise TypeError("map_dict_chunk context must have an attribute 'uniform' that is a cell, not a {}".format(type(hc.uniform)))
            ctx.uniform.connect(hc.uniform)
            con = ["..uniform"], ["ctx", subctx, "uniform"]
            pseudo_connections.append(con)

        if first:
            if isinstance(hci, StructuredCell):
                raise TypeError("map_dict_chunk context has a cell called 'inp', but its celltype must be mixed, not structured")
            if not isinstance(hci, CoreCell):
                raise TypeError("map_dict_chunk context must have an attribute 'inp' that is a cell, not a {}".format(type(hci)))
            if hci.celltype != "mixed":
                raise TypeError("map_dict_chunk context has a cell called 'inp', but its celltype must be mixed, not {}".format(hci.celltype))

        con = ["..inp"], ["ctx", subctx, "inp"]
        pseudo_connections.append(con)

        inputchunk = {k:inp[k] for k in inpkeys[pos:pos+chunksize]}
        #print("CHUNK", list(inputchunk.keys()))

        chunk_ctx = context()
        setattr(ctx, "chunk_%d" % (n+1), chunk_ctx)
        chunk_ctx.inputchunk_checksum = cell("checksum")
        chunk_ctx.inputchunk_checksum.set(inputchunk)
        chunk_ctx.inputchunk = cell("mixed", hash_pattern={"*": "#"})
        chunk_ctx.inputchunk_checksum.connect(chunk_ctx.inputchunk)

        if first:
            if not hasattr(hc, "result"):
                raise TypeError("map_dict_chunk context must have a cell called 'result'")
            if isinstance(hc.result, StructuredCell):
                raise TypeError("map_dict_chunk context has a cell called 'result', but its celltype must be mixed, not structured")
            if not isinstance(hc.result, CoreCell):
                raise TypeError("map_dict_chunk context must have an attribute 'result' that is a cell, not a {}".format(type(hc.result)))

        chunk_ctx.inputchunk.connect(hci)
        chunk_ctx.result = cell("mixed", hash_pattern = {"*": "#"})
        chunk_ctx.result_checksum = cell("checksum")
        chunk_ctx.result_deep = cell("plain")
        hc.result.connect(chunk_ctx.result)
        chunk_ctx.result.connect(chunk_ctx.result_checksum)
        chunk_ctx.result_checksum.connect(chunk_ctx.result_deep)
        chunk_ctx.result_deep.connect(ctx.sc.inchannels[(n+1,)])
        con = ["ctx", subctx, "result"], ["..result"]
        pseudo_connections.append(con)
        first = False

    ctx.subresults = cell("plain")
    ctx.sc.outchannels[()].connect(ctx.subresults)

    merge_subresults = lib_module_dict["helper"]["merge_subresults_chunk"]
    ctx.merge_subresults = transformer({
        "subresults": {"io": "input", "celltype": "plain"},
        "result": {"io": "output", "celltype": "checksum"}
    })
    ctx.merge_subresults.code.cell().set(merge_subresults)
    ctx.subresults.connect(ctx.merge_subresults.subresults)
    ctx.result_checksum = cell("checksum")
    ctx.merge_subresults.result.connect(ctx.result_checksum)
    ctx.result = cell("mixed", hash_pattern={"*": "#"})
    ctx.result_checksum.connect(ctx.result)


    if not elision:
        ctx._pseudo_connections = pseudo_connections

def map_dict_chunk_nested(
  ctx, chunksize, elision, elision_chunksize, graph, inp, keyorder,
  *, lib_module_dict, lib_codeblock, lib, has_uniform
):
    from seamless.core import cell, macro, context, path, transformer
    assert len(inp) == len(keyorder)
    length = len(inp)
    #print("NEST", length, keyorder[0])

    if elision and elision_chunksize > 1 and length > elision_chunksize * chunksize:
        merge_subresults = lib_module_dict["helper"]["merge_subresults_dict"]
        ctx.lib_module_dict = cell("plain").set(lib_module_dict)
        ctx.lib_codeblock = cell("plain").set(lib_codeblock)
        ctx.main_code = cell("python").set(lib_module_dict["map_dict_chunk"]["main"])
        ctx.lib_module = cell("plain").set({
            "type": "interpreted",
            "language": "python",
            "code": lib_codeblock
        })
        ctx.graph = cell("plain").set(graph)
        ctx.elision = cell("bool").set(elision)
        ctx.chunksize = cell("int").set(chunksize)
        ctx.elision_chunksize = cell("int").set(elision_chunksize)
        ctx.has_uniform = cell("bool").set(has_uniform)        
        chunk_index = 0

        macro_params = {
            'chunksize': {'celltype': 'int'},
            'elision_': {'celltype': 'bool'},
            'elision_chunksize': {'celltype': 'int'},
            'graph': {'celltype': 'plain'},
            'lib_module_dict': {'celltype': 'plain'},
            'lib_codeblock': {'celltype': 'plain'},
            'lib': {'celltype': 'plain', 'subcelltype': 'module'},
            'inp': {'celltype': 'plain'},
            'has_uniform': {'celltype': 'bool'},
            'keyorder': {'celltype': 'plain'},
        }

        if has_uniform:
            ctx.uniform = cell("mixed")
        subresults = {}
        chunksize2 = chunksize
        while chunksize2 * elision_chunksize < length:
            chunksize2 *= elision_chunksize
        for n in range(0, length, chunksize2):
            chunk_keyorder = keyorder[n:n+chunksize2]
            chunk_inp = {k: inp[k] for k in chunk_keyorder}
            chunk_index += 1
            subresult = cell("checksum")

            m = macro(macro_params)
            m.allow_elision = True

            setattr(ctx, "m{}".format(chunk_index), m)
            ctx.main_code.connect(m.code)
            ctx.chunksize.connect(m.chunksize)
            ctx.elision.connect(m.elision_)
            ctx.elision_chunksize.connect(m.elision_chunksize)
            ctx.has_uniform.connect(m.has_uniform)
            ctx.graph.connect(m.graph)
            ctx.lib_module_dict.connect(m.lib_module_dict)
            ctx.lib_codeblock.connect(m.lib_codeblock)
            ctx.lib_module.connect(m.lib)
            m.inp.cell().set(chunk_inp)
            m.keyorder.cell().set(chunk_keyorder)
            subr = "subresult{}".format(chunk_index)
            setattr(ctx, subr, subresult)
            subresults[subr] = subresult
            result_path = path(m.ctx).result
            result_path.connect(subresult)
            input_cells = {}
            if has_uniform:
                uniform_path = path(m.ctx).uniform
                ctx.uniform.connect(uniform_path)
                input_cells = {ctx.uniform: uniform_path}

            ctx._get_manager().set_elision(
                macro=m,
                input_cells=input_cells,
                output_cells={subresult: result_path,}
            )

        transformer_params = {}
        for subr in subresults:
            transformer_params[subr] = {"io": "input", "celltype": "checksum"}
        transformer_params["result"] = {"io": "output", "celltype": "checksum"}
        ctx.merge_subresults = transformer(transformer_params)
        ctx.merge_subresults.code.cell().set(merge_subresults)
        tf = ctx.merge_subresults
        for subr,c in subresults.items():
            c.connect(getattr(tf, subr))

        ctx.result = cell("mixed", hash_pattern={"*": "#"})
        tf.result.connect(ctx.result)

    else:
        lib.map_dict_chunk(ctx, chunksize, graph, inp, keyorder, has_uniform, elision, lib_module_dict)
    return ctx

def main(ctx,
  chunksize, elision_, elision_chunksize,
  graph, lib_module_dict, lib_codeblock, inp, keyorder, has_uniform
):
    lib.map_dict_chunk_nested(
        ctx, chunksize, elision_, elision_chunksize, graph, inp,
        lib_module_dict=lib_module_dict,
        lib_codeblock=lib_codeblock,
        lib=lib,has_uniform=has_uniform,
        keyorder=keyorder
    )
    return ctx

def top(ctx, chunksize, elision_, elision_chunksize, graph, lib_module_dict, lib_codeblock, inp, keyorder, has_uniform):
    ctx.lib_module_dict = cell("plain").set(lib_module_dict)
    ctx.lib_codeblock = cell("plain").set(lib_codeblock)
    ctx.main_code = cell("python").set(lib_module_dict["map_dict_chunk"]["main"])
    ctx.lib_module = cell("plain").set({
        "type": "interpreted",
        "language": "python",
        "code": lib_codeblock
    })
    ctx.chunksize = cell("int").set(chunksize)
    ctx.graph = cell("plain").set(graph)
    ctx.elision = cell("bool").set(elision_)
    ctx.elision_chunksize = cell("int").set(elision_chunksize)
    ctx.has_uniform = cell("bool").set(has_uniform)

    if has_uniform:
        ctx.uniform = cell("mixed")

    macro_params = {
        'chunksize': {'celltype': 'int'},
        'elision_': {'celltype': 'bool'},
        'elision_chunksize': {'celltype': 'int'},
        'graph': {'celltype': 'plain'},
        'lib_module_dict': {'celltype': 'plain'},
        'lib_codeblock': {'celltype': 'plain'},
        'lib': {'celltype': 'plain', 'subcelltype': 'module'},
        'inp': {'celltype': 'plain'},
        'keyorder': {'celltype': 'plain'},
        'has_uniform': {'celltype': 'bool'},
    }
    ctx.top = macro(macro_params)
    m = ctx.top
    m.allow_elision = elision_

    ctx.main_code.connect(m.code)
    ctx.chunksize.connect(m.chunksize)
    ctx.elision.connect(m.elision_)
    ctx.elision_chunksize.connect(m.elision_chunksize)
    ctx.has_uniform.connect(m.has_uniform)
    ctx.graph.connect(m.graph)
    ctx.lib_module_dict.connect(m.lib_module_dict)
    ctx.lib_codeblock.connect(m.lib_codeblock)
    ctx.lib_module.connect(m.lib)
    m.inp.cell().set(inp)
    m.keyorder.cell().set(keyorder)
    result_path = path(m.ctx).result
    ctx.result = cell("mixed", hash_pattern={"*": "#"})
    result_path.connect(ctx.result)

    input_cells = {}
    if has_uniform:
        uniform_path = path(m.ctx).uniform
        ctx.uniform.connect(uniform_path)
        input_cells={ctx.uniform: uniform_path}
    ctx._get_manager().set_elision(
        macro=m,
        input_cells=input_cells,
        output_cells={ctx.result: result_path,}
    )
