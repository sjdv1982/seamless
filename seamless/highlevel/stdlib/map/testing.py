import seamless.core.execute
seamless.core.execute.DIRECT_PRINT = True

def test(mylib):
    print("test map_list")
    test_map_list(mylib)
    print("test map_list uniform")
    test_map_list_uniform(mylib)
    print("test map_list_N")
    test_map_list_N(mylib)
    print("test map_list_N uniform")
    test_map_list_N_uniform(mylib)
    print("test map_dict")
    test_map_dict(mylib)
    print("test map_dict uniform")
    test_map_dict_uniform(mylib)
    print("test map_dict_chunk")
    test_map_dict_chunk(mylib)
    print("test map_dict_chunk uniform")
    test_map_dict_chunk_uniform(mylib)

def test_map_list_N(mylib):
    from seamless.highlevel import Context, Cell
    ctx = Context()
    ctx.include(mylib.map_list_N)

    ctx.add = Context()
    ctx.add.inp = Context()
    ctx.add.inp.a = Cell("mixed")
    ctx.add.inp.b = Cell("mixed")
    def add(a, b):
        print("ADD", a, b)
        return a + b
    ctx.add.tf = add
    ctx.add.tf.a = ctx.add.inp.a
    ctx.add.tf.b = ctx.add.inp.b
    ctx.add.result = ctx.add.tf
    ctx.add.result.celltype = "int"
    ctx.compute()

    ctx.a = [10,20,30,40]
    ctx.a.hash_pattern = {"!": "#"}
    ctx.b = [2,4,8,12]
    ctx.b.hash_pattern = {"!": "#"}
    ctx.result = Cell()

    ctx.mapping = ctx.lib.map_list_N(
        context_graph=ctx.add,
        inp = {
            "a": ctx.a,
            "b": ctx.b,
        },
        result = ctx.result,
        elision = True,
        elision_chunksize = 2
    )
    ctx.compute()
    print(ctx.result.value)
    ctx.a += [80, 12, 1, 1, 10,20,30,40]
    ctx.b += [100, 16, 3, 3, 2,4,8,12]
    ctx.compute()
    print(ctx.result.value)

def test_map_list_N_uniform(mylib):
    from seamless.highlevel import Context, Cell
    ctx = Context()
    ctx.include(mylib.map_list_N)

    ctx.add = Context()
    ctx.add.uniform = Cell("mixed")
    ctx.add.inp = Context()
    ctx.add.inp.a = Cell("mixed")
    ctx.add.inp.b = Cell("mixed")
    def add(a, b, c):
        print("ADD", a, b, c)
        return a + b + c
    ctx.add.tf = add
    ctx.add.tf.a = ctx.add.inp.a
    ctx.add.tf.b = ctx.add.inp.b
    ctx.add.tf.c = ctx.add.uniform
    ctx.add.result = ctx.add.tf
    ctx.add.result.celltype = "int"
    ctx.compute()

    ctx.a = [110,120,130,140]
    ctx.a.hash_pattern = {"!": "#"}
    ctx.b = [2,4,8,12]
    ctx.b.hash_pattern = {"!": "#"}
    ctx.c = 7000
    ctx.result = Cell()

    ctx.mapping = ctx.lib.map_list_N(
        context_graph=ctx.add,
        inp = {
            "a": ctx.a,
            "b": ctx.b,
        },
        uniform = ctx.c,
        result = ctx.result,
        elision = True,
        elision_chunksize = 2
    )
    ctx.compute()
    print(ctx.result.value)
    ctx.c = 8000
    ctx.compute()
    print(ctx.result.value)

def test_map_list(mylib):
    from seamless.highlevel import Context, Cell
    ctx = Context()
    ctx.include(mylib.map_list)

    ctx.add = Context()
    ctx.add.inp = Cell("mixed")
    def add(a, b):
        print("ADD", a, b)
        return a + b
    ctx.add.tf = add
    ctx.add.tf.a = ctx.add.inp
    ctx.add.tf.b = 1000
    ctx.add.result = ctx.add.tf
    ctx.add.result.celltype = "int"
    ctx.compute()

    ctx.inp = [10,20,30,40]
    ctx.inp.hash_pattern = {"!": "#"}
    ctx.result = Cell()

    ctx.mapping = ctx.lib.map_list(
        context_graph=ctx.add,
        inp = ctx.inp,
        result = ctx.result,
        elision = True,
        elision_chunksize = 2
    )
    ctx.compute()
    print(ctx.mapping.ctx.m.exception)
    print(ctx.result.value)
    ctx.inp += [80, 12, 1, 1, 10,20,30,40]
    ctx.compute()
    print(ctx.result.value)


def test_map_list_uniform(mylib):
    from seamless.highlevel import Context, Cell
    ctx = Context()
    ctx.include(mylib.map_list)

    ctx.b = -1000
    ctx.uniform = Cell()
    ctx.uniform.b = ctx.b

    ctx.add = Context()
    ctx.add.inp = Cell("mixed")
    ctx.add.uniform = Cell("mixed")
    ctx.add.uniform2 = ctx.add.uniform
    def add(a, b):
        print("ADD", a, b)
        return a + b
    ctx.add.tf = add
    ctx.add.tf.a = ctx.add.inp
    ctx.add.tf.b = ctx.add.uniform2.b
    ctx.add.result = ctx.add.tf
    ctx.add.result.celltype = "int"
    ctx.compute()

    ctx.inp = [210,220,230,240]
    ctx.inp.hash_pattern = {"!": "#"}
    ctx.result = Cell()

    ctx.mapping = ctx.lib.map_list(
        context_graph=ctx.add,
        inp = ctx.inp,
        uniform = ctx.uniform,
        result = ctx.result,
        elision = True,
        elision_chunksize = 2
    )
    ctx.compute()
    print(ctx.mapping.ctx.m.exception)
    print(ctx.result.value)
    ctx.b = 1000
    ctx.compute()
    print(ctx.result.value)

def test_map_dict(mylib):
    from seamless.highlevel import Context, Cell
    ctx = Context()
    ctx.include(mylib.map_dict)

    ctx.add = Context()
    ctx.add.inp = Cell("mixed")
    def add(a, b):
        print("ADD", a, b)
        return a + b
    ctx.add.tf = add
    ctx.add.tf.a = ctx.add.inp
    ctx.add.tf.b = 1000
    ctx.add.result = ctx.add.tf
    ctx.add.result.celltype = "int"
    ctx.compute()

    ctx.inp = {"key1": 10, "key2": 220, "key3": 30, "key4": 40}
    ctx.inp.hash_pattern = {"*": "#"}
    ctx.result = Cell()
    ctx.keyorder = Cell("plain")

    ctx.mapping = ctx.lib.map_dict(
        context_graph=ctx.add,
        inp = ctx.inp,
        keyorder0 = [],
        keyorder = ctx.keyorder,
        result = ctx.result,
        elision = True,
        elision_chunksize = 2
    )
    ctx.compute()
    print(ctx.mapping.ctx.status)
    print(ctx.mapping.ctx.m.ctx.top.exception)
    print(ctx.result.value)
    ctx.mapping.keyorder0 = ctx.keyorder.value
    ctx.compute()
    print(ctx.result.value)
    inp = ctx.inp.value
    inp.update({
        "a": 80,
        "b": 30,
        "c": 999,
        "d": -1,
    })
    ctx.inp = inp
    ctx.compute()
    print(ctx.result.value)
    print(ctx.keyorder.value)

def test_map_dict_uniform(mylib):
    from seamless.highlevel import Context, Cell
    ctx = Context()
    ctx.include(mylib.map_dict)

    ctx.b = 1000

    ctx.add = Context()
    ctx.add.inp = Cell("mixed")
    ctx.add.uniform = Cell("mixed")
    def add(a, b):
        print("ADD", a, b)
        return a + b
    ctx.add.tf = add
    ctx.add.tf.a = ctx.add.inp
    ctx.add.tf.b = ctx.add.uniform
    ctx.add.result = ctx.add.tf
    ctx.add.result.celltype = "int"
    ctx.compute()

    ctx.inp = {"key1": 10, "key2": 220, "key3": 30, "key4": 40}
    ctx.inp.hash_pattern = {"*": "#"}
    ctx.result = Cell()
    ctx.keyorder = Cell("plain")

    ctx.mapping = ctx.lib.map_dict(
        context_graph=ctx.add,
        inp = ctx.inp,
        uniform = ctx.b,
        keyorder0 = [],
        keyorder = ctx.keyorder,
        result = ctx.result,
        elision = True,
        elision_chunksize = 2
    )
    ctx.compute()
    print(ctx.mapping.ctx.status)
    print(ctx.mapping.ctx.m.ctx.top.exception)
    print(ctx.result.value)
    ctx.b = 6000
    ctx.compute()
    print(ctx.result.value)

def test_map_dict_chunk(mylib):
    from seamless.highlevel import Context, Cell
    ctx = Context()
    ctx.include(mylib.map_dict_chunk)

    ctx.mul = Context()
    ctx.mul.inp = Cell("mixed")
    def mul(a, factor):
        print("MUL", a)
        result = {}
        for key in a:
            result[key] = a[key] * factor
        return result
    ctx.mul.tf = mul
    ctx.mul.tf.a = ctx.mul.inp
    ctx.mul.tf.factor = 3
    ctx.mul.result = ctx.mul.tf
    ctx.mul.result.celltype = "mixed"
    ctx.compute()

    ctx.inp = {"key1": 10, "key2": 220, "key3": 30, "key4": 40}
    ctx.inp.hash_pattern = {"*": "#"}
    ctx.result = Cell()
    ctx.keyorder = Cell("plain")

    ctx.mapping = ctx.lib.map_dict_chunk(
        context_graph=ctx.mul,
        inp = ctx.inp,
        chunksize = 2,
        keyorder0 = [],
        keyorder = ctx.keyorder,
        result = ctx.result,
        elision = True,
        elision_chunksize = 3
    )
    ctx.compute()
    print(ctx.mapping.ctx.status)
    print(ctx.result.value)
    ctx.mapping.keyorder0 = ctx.keyorder.value
    ctx.compute()
    print(ctx.result.value)    
    inp = ctx.inp.value
    inp.update({
        "a": 80,
        "b": 30,
        "c": 999,
        "d": -1,
    })
    ctx.inp = inp
    ctx.compute()
    print(ctx.result.value)
    print(ctx.keyorder.value)

def test_map_dict_chunk_uniform(mylib):
    from seamless.highlevel import Context, Cell
    ctx = Context()
    ctx.include(mylib.map_dict_chunk)

    ctx.factor = 7

    ctx.mul = Context()
    ctx.mul.inp = Cell("mixed")
    ctx.mul.uniform = Cell("mixed")
    def mul(a, factor):
        print("MUL", a, factor)
        result = {}
        for key in a:
            result[key] = a[key] * factor
        return result
    ctx.mul.tf = mul
    ctx.mul.tf.a = ctx.mul.inp
    ctx.mul.tf.factor = ctx.mul.uniform
    ctx.mul.result = ctx.mul.tf
    ctx.mul.result.celltype = "mixed"
    ctx.compute()

    ctx.inp = {"key1": 10, "key2": 220, "key3": 30, "key4": 40}
    ctx.inp.hash_pattern = {"*": "#"}
    ctx.result = Cell()
    ctx.keyorder = Cell("plain")

    ctx.mapping = ctx.lib.map_dict_chunk(
        context_graph=ctx.mul,
        inp = ctx.inp,
        chunksize = 2,
        keyorder0 = [],
        keyorder = ctx.keyorder,
        uniform = ctx.factor,
        result = ctx.result,
        elision = True,
        elision_chunksize = 3
    )
    ctx.compute()
    print(ctx.mapping.ctx.status)
    print(ctx.result.value)
    ctx.factor = 13
    ctx.compute()
    print(ctx.result.value)
