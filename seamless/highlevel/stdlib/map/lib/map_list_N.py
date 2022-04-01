def map_list_N(ctx, graph, inp, has_uniform, elision):
    #print("map_list_N", inp)
    from seamless.core import Cell as CoreCell
    from seamless.core import cell
    from seamless.core.structured_cell import StructuredCell
    from seamless.core.HighLevelContext import HighLevelContext
    from seamless.core.unbound_context import UnboundContext
    
    first_k = list(inp.keys())[0]
    length = len(inp[first_k])
    for k in inp:
        if len(inp[k]) != length:
            err = "all cells in inp must have the same length, but '{}' has length {} while '{}' has length {}"
            raise ValueError(err.format(k, len(inp[k]), first_k, length))

    pseudo_connections = []
    ctx.result = cell("mixed", hash_pattern = {"!": "#"})

    ctx.sc_data = cell("mixed", hash_pattern = {"!": "#"})
    ctx.sc_buffer = cell("mixed", hash_pattern = {"!": "#"})
    ctx.sc = StructuredCell(
        data=ctx.sc_data,
        buffer=ctx.sc_buffer,
        inchannels=[(n,) for n in range(length)],
        outchannels=[()],
        hash_pattern = {"!": "#"}
    )

    if has_uniform:
        ctx.uniform = cell("mixed")

    for n in range(length):
        hc = HighLevelContext(graph)

        subctx = "subctx%d" % (n+1)
        setattr(ctx, subctx, hc)

        if n == 0:
            if not hasattr(hc, "inp"):
                raise TypeError("map_list_N context must have a subcontext called 'inp'")
            hci = hc.inp
            if not isinstance(hci, UnboundContext):
                raise TypeError("map_list_N context must have an attribute 'inp' that is a context, not a {}".format(type(hci)))
        else:
            hci = hc.inp

        for k in inp:
            if n == 0:
                if not hasattr(hci, k):
                    raise TypeError("map_list_N context must have a cell called inp.'{}'".format(k))
                if isinstance(hci[k], StructuredCell):
                    raise TypeError("map_list_N context has a cell called inp.'{}', but its celltype must be mixed, not structured".format(k))
                if not isinstance(hci[k], CoreCell):
                    raise TypeError("map_list_N context must have an attribute inp.'{}' that is a cell, not a {}".format(k, type(hci[k])))
                if hci[k].celltype != "mixed":
                    raise TypeError("map_list_N context has a cell called inp.'{}', but its celltype must be mixed, not {}".format(k, hci[k].celltype))

            con = [".." + k], ["ctx", subctx, "inp", k]
            pseudo_connections.append(con)
            cs = inp[k][n]
            hci[k].set_checksum(cs)

        if has_uniform:
            if n == 0:
                if not hasattr(hc, "uniform"):
                    raise TypeError("map_list_N context must have a cell called 'uniform'")
                if isinstance(hc.uniform, StructuredCell):
                    raise TypeError("map_list_N context has a cell called 'uniform', but its celltype must be mixed, not structured")
                if not isinstance(hc.uniform, CoreCell):
                    raise TypeError("map_list_N context must have an attribute 'uniform' that is a cell, not a {}".format(type(hc.uniform)))
            ctx.uniform.connect(hc.uniform)
            con = ["..uniform"], ["ctx", subctx, "uniform"]
            pseudo_connections.append(con)

        if n == 0:
            if not hasattr(hc, "result"):
                raise TypeError("map_list_N context must have a cell called 'result'")
            if isinstance(hc.result, StructuredCell):
                raise TypeError("map_list_N context has a cell called 'result', but its celltype must be mixed, not structured")
            if not isinstance(hc.result, CoreCell):
                raise TypeError("map_list_N context must have an attribute 'result' that is a cell, not a {}".format(type(hc.result)))

        resultname = "result%d" % (n+1)
        setattr(ctx, resultname, cell("mixed"))
        c = getattr(ctx, resultname)
        hc.result.connect(c)
        c.connect(ctx.sc.inchannels[(n,)])
        con = ["ctx", subctx, "result"], ["..result"]
        pseudo_connections.append(con)

    ctx.sc.outchannels[()].connect(ctx.result)
    if not elision:
        ctx._pseudo_connections = pseudo_connections

def map_list_N_nested(
  ctx, elision, elision_chunksize, graph, inp,
  *, lib_module_dict, lib_codeblock, lib, has_uniform
):
    from seamless.core import cell, macro, context, path, transformer
    first_k = list(inp.keys())[0]
    length = len(inp[first_k])
    #print("NEST", length, inp[first_k][0])
    for k in inp:
        if len(inp[k]) != length:
            err = "all cells in inp must have the same length, but '{}' has length {} while '{}' has length {}"
            raise ValueError(err.format(k, len(inp[k]), first_k, length))

    if elision and elision_chunksize > 1 and length > elision_chunksize:
        merge_subresults = lib_module_dict["helper"]["merge_subresults_list"]
        ctx.lib_module_dict = cell("plain").set(lib_module_dict)
        ctx.lib_codeblock = cell("plain").set(lib_codeblock)
        ctx.main_code = cell("python").set(lib_module_dict["map_list_N"]["main"])
        ctx.lib_module = cell("plain").set({
            "type": "interpreted",
            "language": "python",
            "code": lib_codeblock
        })
        ctx.graph = cell("plain").set(graph)
        ctx.elision = cell("bool").set(elision)
        ctx.elision_chunksize = cell("int").set(elision_chunksize)
        ctx.has_uniform = cell("bool").set(has_uniform)
        chunk_index = 0

        macro_params = {
            'elision_': {'celltype': 'bool'},
            'elision_chunksize': {'celltype': 'int'},
            'graph': {'celltype': 'plain'},
            "lib_module_dict": {'celltype': 'plain'},
            "lib_codeblock": {'celltype': 'plain'},
            "lib": {'celltype': 'plain', 'subcelltype': 'module'},
            'inp': {'celltype': 'checksum'},
            'has_uniform': {'celltype': 'bool'},
        }

        if has_uniform:
            ctx.uniform = cell("mixed")
        subresults = {}
        chunksize = elision_chunksize
        while chunksize * elision_chunksize < length:
            chunksize *= elision_chunksize
        for n in range(0, length, chunksize):
            chunk_inp = {}
            for k in inp:
                chunk_inp[k] = inp[k][n:n+chunksize]
            chunk_index += 1
            subresult = cell("checksum")

            m = macro(macro_params)
            m.allow_elision = True

            setattr(ctx, "m{}".format(chunk_index), m)
            ctx.main_code.connect(m.code)
            ctx.elision.connect(m.elision_)
            ctx.elision_chunksize.connect(m.elision_chunksize)
            ctx.has_uniform.connect(m.has_uniform)
            ctx.graph.connect(m.graph)
            ctx.lib_module_dict.connect(m.lib_module_dict)
            ctx.lib_codeblock.connect(m.lib_codeblock)
            ctx.lib_module.connect(m.lib)
            m.inp.cell().set(chunk_inp)
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

        ctx.result = cell("mixed", hash_pattern={"!": "#"})
        tf.result.connect(ctx.result)

    else:
        lib.map_list_N(ctx, graph, inp, has_uniform, elision)
    return ctx

def main(ctx, elision_, elision_chunksize, graph, lib_module_dict, lib_codeblock, inp, has_uniform):
    lib.map_list_N_nested(
        ctx, elision_, elision_chunksize, graph, inp,
        lib_module_dict=lib_module_dict,
        lib_codeblock=lib_codeblock,
        lib=lib, has_uniform=has_uniform
    )
    return ctx

def top(ctx, elision_, elision_chunksize, graph, lib_module_dict, lib_codeblock, inp, has_uniform):
    ctx.lib_module_dict = cell("plain").set(lib_module_dict)
    ctx.lib_codeblock = cell("plain").set(lib_codeblock)
    ctx.main_code = cell("python").set(lib_module_dict["map_list_N"]["main"])
    ctx.lib_module = cell("plain").set({
        "type": "interpreted",
        "language": "python",
        "code": lib_codeblock
    })
    ctx.graph = cell("plain").set(graph)
    ctx.elision = cell("bool").set(elision_)
    ctx.elision_chunksize = cell("int").set(elision_chunksize)
    ctx.has_uniform = cell("bool").set(has_uniform)

    if has_uniform:
        ctx.uniform = cell("mixed")

    macro_params = {
        'elision_': {'celltype': 'bool'},
        'elision_chunksize': {'celltype': 'int'},
        'graph': {'celltype': 'plain'},
        'lib_module_dict': {'celltype': 'plain'},
        'lib_codeblock': {'celltype': 'plain'},
        'lib': {'celltype': 'plain', 'subcelltype': 'module'},
        'inp': {'celltype': 'plain'},
        'has_uniform': {'celltype': 'bool'},
    }
    ctx.top = macro(macro_params)
    m = ctx.top
    m.allow_elision = elision_

    ctx.main_code.connect(m.code)
    ctx.elision.connect(m.elision_)
    ctx.elision_chunksize.connect(m.elision_chunksize)
    ctx.has_uniform.connect(m.has_uniform)
    ctx.graph.connect(m.graph)
    ctx.lib_module_dict.connect(m.lib_module_dict)
    ctx.lib_codeblock.connect(m.lib_codeblock)
    ctx.lib_module.connect(m.lib)
    m.inp.cell().set(inp)
    result_path = path(m.ctx).result
    ctx.result = cell("mixed", hash_pattern={"!": "#"})
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
