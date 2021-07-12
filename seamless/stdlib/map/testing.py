def test(mylib):
    print("test map_list")
    test_map_list(mylib)
    print("test map_list_N")
    test_map_list_N(mylib)
    print("test map_dict")
    test_map_dict(mylib)
    print("test map_dict_chunk")
    test_map_dict_chunk(mylib)

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
    raise NotImplementedError ###ctx.add.tf.debug = True
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
    ###ctx.a += [80, 12, 1, 1, 10,20,30,40]  # TODO: bugged (?)
    ctx.a = ctx.a.value +[80, 12, 1, 1, 10,20,30,40]
    ###ctx.b += [100, 16, 3, 3, 2,4,8,12]  # TODO: bugged (?)
    ctx.b = ctx.b.value + [100, 16, 3, 3, 2,4,8,12]
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
    raise NotImplementedError ###ctx.add.tf.debug = True
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
    ctx.inp = ctx.inp.value + [80, 12, 1, 1, 10,20,30,40]  # TODO: += is bugged
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
    raise NotImplementedError ###ctx.add.tf.debug = True
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
    raise NotImplementedError ###ctx.mul.tf.debug = True
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
    print(ctx.mapping.ctx.m.ctx.top.exception)
    print(ctx.result.value)
    ctx.mapping.keyorder0 = ctx.keyorder.value
    ctx.compute()
    print(ctx.result.value)
    print("UP")
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