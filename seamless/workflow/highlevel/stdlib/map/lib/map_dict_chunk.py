def map_dict_chunk(
    ctx,
    chunksize,
    graph,
    inp,
    keyorder,
    has_uniform,
    elision,
    merge_method,
    lib_module_dict,
):
    # print("map_dict_chunk", inp)
    from seamless.core import Cell as CoreCell
    from seamless.core import cell, context, transformer
    from seamless.core.structured_cell import StructuredCell
    from seamless.core.HighLevelContext import HighLevelContext
    import math

    pseudo_connections = []
    inpkeys = keyorder
    nchunks = math.ceil(len(inpkeys) / chunksize)
    # sc: a cell that holds literal checksums
    ctx.sc_data = cell("mixed")
    ctx.sc_buffer = cell("mixed")
    ctx.sc = StructuredCell(
        data=ctx.sc_data,
        buffer=ctx.sc_buffer,
        inchannels=[(n + 1,) for n in range(nchunks)],
        outchannels=[()],
        validate_inchannels=False,
    )

    if has_uniform:
        ctx.uniform = cell("mixed")

    first = True
    for n in range(nchunks):
        pos = chunksize * n
        hc = HighLevelContext(graph)

        subctx = "subctx_{:05d}".format(n + 1)
        setattr(ctx, subctx, hc)

        if first:
            if not hasattr(hc, "inp"):
                raise TypeError("map_dict_chunk context must have a cell called 'inp'")
        hci = hc.inp

        if has_uniform:
            if first:
                if not hasattr(hc, "uniform"):
                    raise TypeError(
                        "map_dict_chunk context must have a cell called 'uniform'"
                    )
                if isinstance(hc.uniform, StructuredCell):
                    raise TypeError(
                        "map_dict_chunk context has a cell called 'uniform', but its celltype must be mixed, not structured"
                    )
                if not isinstance(hc.uniform, CoreCell):
                    raise TypeError(
                        "map_dict_chunk context must have an attribute 'uniform' that is a cell, not a {}".format(
                            type(hc.uniform)
                        )
                    )
            ctx.uniform.connect(hc.uniform)
            con = ["..uniform"], ["ctx", subctx, "uniform"]
            pseudo_connections.append(con)

        if first:
            if isinstance(hci, StructuredCell):
                raise TypeError(
                    "map_dict_chunk context has a cell called 'inp', but its celltype must be mixed, not structured"
                )
            if not isinstance(hci, CoreCell):
                raise TypeError(
                    "map_dict_chunk context must have an attribute 'inp' that is a cell, not a {}".format(
                        type(hci)
                    )
                )
            if hci.celltype not in ("mixed", "deepcell"):
                raise TypeError(
                    "map_dict_chunk context has a cell called 'inp', but its celltype must be mixed or deepcell, not {}".format(
                        hci.celltype
                    )
                )

        con = ["..inp"], ["ctx", subctx, "inp"]
        pseudo_connections.append(con)

        inputchunk = {k: inp[k] for k in inpkeys[pos : pos + chunksize]}
        # print("CHUNK", list(inputchunk.keys()))

        chunk_ctx = context()
        setattr(ctx, "chunk_{:05d}".format(n + 1), chunk_ctx)
        chunk_ctx.inputchunk_checksum = cell("checksum")
        chunk_ctx.inputchunk_checksum.set(inputchunk)
        chunk_ctx.inputchunk = cell("mixed", hash_pattern={"*": "#"})
        chunk_ctx.inputchunk_checksum.connect(chunk_ctx.inputchunk)

        if first:
            if not hasattr(hc, "result"):
                raise TypeError(
                    "map_dict_chunk context must have a cell called 'result'"
                )
        hcr = hc.result
        if first:
            if isinstance(hcr, StructuredCell):
                raise TypeError(
                    "map_dict_chunk context has a cell called 'result', but its celltype must be mixed, not structured"
                )
            if not isinstance(hcr, CoreCell):
                raise TypeError(
                    "map_dict_chunk context must have an attribute 'result' that is a cell, not a {}".format(
                        type(hcr)
                    )
                )

            if hcr.celltype not in ("mixed", "deepcell"):
                raise TypeError(
                    "map_dict_chunk context has a cell called 'result', but its celltype must be mixed or deepcell, not {}".format(
                        hci.celltype
                    )
                )

        chunk_ctx.inputchunk.connect(hci)
        if hcr.celltype == "deepcell" or merge_method == "deepcell":
            chunk_ctx.result = cell("mixed", hash_pattern={"*": "#"})
        else:
            chunk_ctx.result = cell("mixed")
        hcr.connect(chunk_ctx.result)
        if merge_method == "deepcell":
            chunk_ctx.result_checksum = cell("checksum")
            chunk_ctx.result_deep = cell("plain")
            chunk_ctx.result.connect(chunk_ctx.result_checksum)
            chunk_ctx.result_checksum.connect(chunk_ctx.result_deep)
            chunk_ctx.result_deep.connect(ctx.sc.inchannels[(n + 1,)])
        elif merge_method == "dict" or merge_method == "list":
            chunk_ctx.result.connect(ctx.sc.inchannels[(n + 1,)])
        else:
            raise ValueError(merge_method)
        con = ["ctx", subctx, "result"], ["..result"]
        pseudo_connections.append(con)
        first = False

    if merge_method == "deepcell":
        ctx.subresults = cell("plain")
    elif merge_method == "dict" or merge_method == "list":
        ctx.subresults = cell("mixed")
    else:
        raise ValueError(merge_method)
    ctx.sc.outchannels[()].connect(ctx.subresults)

    if merge_method == "deepcell":
        merge_subresults = lib_module_dict["helper"]["merge_subresults_chunk"]
        ctx.merge_subresults = transformer(
            {
                "subresults": {"io": "input", "celltype": "plain"},
                "result": {"io": "output", "celltype": "checksum"},
            }
        )
        ctx.merge_subresults.code.cell().set(merge_subresults)
        ctx.subresults.connect(ctx.merge_subresults.subresults)
        ctx.result_checksum = cell("checksum")
        ctx.merge_subresults.result.connect(ctx.result_checksum)
        ctx.result = cell("mixed", hash_pattern={"*": "#"})
        ctx.result_checksum.connect(ctx.result)

    elif merge_method == "dict" or merge_method == "list":
        if merge_method == "dict":
            merge_subresults = lib_module_dict["helper"]["merge_subresults_chunk"]
        else:
            merge_subresults = lib_module_dict["helper"]["merge_subresults_chunk_list"]
        ctx.merge_subresults = transformer(
            {
                "subresults": {"io": "input", "celltype": "mixed"},
                "result": {"io": "output", "celltype": "mixed"},
            }
        )
        ctx.merge_subresults.code.cell().set(merge_subresults)
        ctx.subresults.connect(ctx.merge_subresults.subresults)
        ctx.result = cell("mixed")
        ctx.merge_subresults.result.connect(ctx.result)

    else:
        raise ValueError(merge_method)

    if not elision:
        ctx._pseudo_connections = pseudo_connections


def map_dict_chunk_nested(
    ctx,
    chunksize,
    elision,
    elision_chunksize,
    graph,
    inp,
    keyorder,
    *,
    lib_module_dict,
    lib_codeblock,
    lib,
    has_uniform,
    merge_method
):
    from seamless.core import cell, macro, context, path, transformer

    assert len(inp) == len(keyorder)
    length = len(inp)
    # print("NEST", length, keyorder[0])

    if elision and elision_chunksize > 1 and length > elision_chunksize * chunksize:
        if merge_method in ("deepcell", "dict"):
            merge_subresults = lib_module_dict["helper"]["merge_subresults_dict"]
        elif merge_method == "list":
            merge_subresults = lib_module_dict["helper"]["merge_subresults_list"]
        else:
            raise ValueError(merge_method)
        ctx.lib_module_dict = cell("plain").set(lib_module_dict)
        ctx.lib_codeblock = cell("plain").set(lib_codeblock)
        ctx.main_code = cell("python").set(lib_module_dict["map_dict_chunk"]["main"])
        ctx.lib_module = cell("plain").set(
            {"type": "interpreted", "language": "python", "code": lib_codeblock}
        )
        ctx.graph = cell("plain").set(graph)
        ctx.elision = cell("bool").set(elision)
        ctx.chunksize = cell("int").set(chunksize)
        ctx.elision_chunksize = cell("int").set(elision_chunksize)
        ctx.has_uniform = cell("bool").set(has_uniform)
        ctx.merge_method = cell("str").set(merge_method)
        chunk_index = 0

        macro_params = {
            "chunksize": {"celltype": "int"},
            "elision_": {"celltype": "bool"},
            "elision_chunksize": {"celltype": "int"},
            "graph": {"celltype": "plain"},
            "lib_module_dict": {"celltype": "plain"},
            "lib_codeblock": {"celltype": "plain"},
            "lib": {"celltype": "plain", "subcelltype": "module"},
            "inp": {"celltype": "plain"},
            "has_uniform": {"celltype": "bool"},
            "keyorder": {"celltype": "plain"},
            "merge_method": {"celltype": "str"},
        }

        if has_uniform:
            ctx.uniform = cell("mixed")
        subresults = {}
        chunksize2 = chunksize
        while chunksize2 * elision_chunksize < length:
            chunksize2 *= elision_chunksize
        for n in range(0, length, chunksize2):
            chunk_keyorder = keyorder[n : n + chunksize2]
            chunk_inp = {k: inp[k] for k in chunk_keyorder}
            chunk_index += 1
            subresult = cell("checksum")

            m = macro(macro_params)
            m.allow_elision = True
            ctx.merge_method.connect(m.merge_method)

            setattr(ctx, "m{:05d}".format(chunk_index), m)
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
                output_cells={
                    subresult: result_path,
                },
            )

        transformer_params = {}
        if merge_method == "deepcell":
            merge_celltype = "checksum"
        elif merge_method == "dict" or merge_method == "list":
            merge_celltype = "mixed"
        else:
            raise ValueError(merge_method)
        for subr in subresults:
            transformer_params[subr] = {"io": "input", "celltype": merge_celltype}
        transformer_params["result"] = {"io": "output", "celltype": merge_celltype}
        ctx.merge_subresults = transformer(transformer_params)
        ctx.merge_subresults.code.cell().set(merge_subresults)
        tf = ctx.merge_subresults
        for subr, c in subresults.items():
            c.connect(getattr(tf, subr))

        if merge_method == "deepcell":
            ctx.result = cell("mixed", hash_pattern={"*": "#"})
        elif merge_method == "dict" or merge_method == "list":
            ctx.result = cell("mixed")
        tf.result.connect(ctx.result)

    else:
        lib.map_dict_chunk(
            ctx,
            chunksize,
            graph,
            inp,
            keyorder,
            has_uniform,
            elision,
            merge_method,
            lib_module_dict,
        )
    return ctx


def main(
    ctx,
    chunksize,
    elision_,
    elision_chunksize,
    graph,
    lib_module_dict,
    lib_codeblock,
    inp,
    keyorder,
    has_uniform,
    merge_method,
):
    lib.map_dict_chunk_nested(
        ctx,
        chunksize,
        elision_,
        elision_chunksize,
        graph,
        inp,
        lib_module_dict=lib_module_dict,
        lib_codeblock=lib_codeblock,
        lib=lib,
        has_uniform=has_uniform,
        keyorder=keyorder,
        merge_method=merge_method,
    )
    return ctx


def top(
    ctx,
    chunksize,
    elision_,
    elision_chunksize,
    graph,
    lib_module_dict,
    lib_codeblock,
    inp,
    keyorder,
    has_uniform,
    merge_method,
):
    ctx.lib_module_dict = cell("plain").set(lib_module_dict)
    ctx.lib_codeblock = cell("plain").set(lib_codeblock)
    ctx.main_code = cell("python").set(lib_module_dict["map_dict_chunk"]["main"])
    ctx.lib_module = cell("plain").set(
        {"type": "interpreted", "language": "python", "code": lib_codeblock}
    )
    ctx.chunksize = cell("int").set(chunksize)
    ctx.graph = cell("plain").set(graph)
    ctx.elision = cell("bool").set(elision_)
    ctx.elision_chunksize = cell("int").set(elision_chunksize)
    ctx.has_uniform = cell("bool").set(has_uniform)

    if has_uniform:
        ctx.uniform = cell("mixed")

    macro_params = {
        "chunksize": {"celltype": "int"},
        "elision_": {"celltype": "bool"},
        "elision_chunksize": {"celltype": "int"},
        "graph": {"celltype": "plain"},
        "lib_module_dict": {"celltype": "plain"},
        "lib_codeblock": {"celltype": "plain"},
        "lib": {"celltype": "plain", "subcelltype": "module"},
        "inp": {"celltype": "plain"},
        "keyorder": {"celltype": "plain"},
        "has_uniform": {"celltype": "bool"},
        "merge_method": {"celltype": "str"},
    }
    ctx.top = macro(macro_params)
    m = ctx.top
    m.allow_elision = elision_
    ctx.merge_method = cell("str")
    ctx.merge_method.set(merge_method)
    ctx.merge_method.connect(m.merge_method)

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
    ctx.result = cell("mixed")
    if merge_method == "deepcell":
        ctx.result.hash_pattern={"*": "#"}
    result_path.connect(ctx.result)

    input_cells = {}
    if has_uniform:
        uniform_path = path(m.ctx).uniform
        ctx.uniform.connect(uniform_path)
        input_cells = {ctx.uniform: uniform_path}
    ctx._get_manager().set_elision(
        macro=m,
        input_cells=input_cells,
        output_cells={
            ctx.result: result_path,
        },
    )
