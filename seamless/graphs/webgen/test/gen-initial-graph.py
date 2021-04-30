from seamless.highlevel import Context, Cell, Transformer

ctx = Context()

ctx.a = Cell("int").set(10)
ctx.a.share(readonly=False)
ctx.b = Cell("int").set(20)
ctx.b.share(readonly=False)
ctx.c = Cell("int").set(30).share()

ctx.tf = lambda a,b: a+b
ctx.tf.a = ctx.a
ctx.tf.b = ctx.b
ctx.c = ctx.tf

def gen_report(a,b,c):
    headers = [
        {
            "value": "a",
            "text": "First input",
        },
        {
            "value": "b",
            "text": "Second input",
        },
        {
            "value": "c",
            "text": "Output",
        },
    ]
    items = []
    for factor in (1,2,3):
        item = {
            "a": factor * a,
            "b": factor * b,
            "c": factor * c
        }
        items.append(item)
    return {"headers": headers, "items": items}
ctx.gen_report = gen_report
ctx.gen_report.a = ctx.a
ctx.gen_report.b = ctx.b
ctx.gen_report.c = ctx.c
ctx.report = ctx.gen_report
ctx.report.datatype = "plain"
ctx.reportschema = Cell("plain")
ctx.reportschema.mount("datatable-schema.json", "rw")
ctx.translate()
ctx.link(ctx.reportschema, ctx.report.schema)
ctx.report.share()

def save():
    ctx.translate()
    ctx.save_graph("initial-graph.seamless")
    ctx.save_zip("initial-graph.zip")

save()