from seamless.highlevel import Context, Cell
ctx = Context()

# Create first, step, length for sequence A
ctx.a_first = Cell("int").set(5)
ctx.a_first.share(readonly=False)
ctx.a_step = Cell("int").set(3)
ctx.a_step.share(readonly=False)
ctx.a_length = Cell("int").set(5)
ctx.a_length.share(readonly=False)

ctx.a = Cell()
ctx.a.first = ctx.a_first
ctx.a.step = ctx.a_step
ctx.a.length = ctx.a_length

def validate(self):
    assert self.first > 0
    assert self.step > 0
    assert self.length > 0

ctx.schema = Cell("plain")
ctx.translate()
ctx.link(ctx.a.schema, ctx.schema)
ctx.a.example.first = 0
ctx.a.example.step = 0
ctx.a.example.length = 0
ctx.a.add_validator(validate, "validate")


ctx.b_first = Cell("int").set(8)
ctx.b_first.share(readonly=False)
ctx.b_step = Cell("int").set(1)
ctx.b_step.share(readonly=False)
ctx.b_length = Cell("int").set(4)
ctx.b_length.share(readonly=False)

ctx.b = Cell()
ctx.translate()
ctx.link(ctx.b.schema, ctx.schema)
ctx.b.first = ctx.b_first
ctx.b.step = ctx.b_step
ctx.b.length = ctx.b_length

def calc_bits(a, b):
    import numpy as np
    result = np.zeros((a.length*b.length, 3),int)
    count = 0
    aa = a.first.unsilk    
    for apos in range(a.length):
        bb = b.first.unsilk
        for bpos in range(b.length):
            mul = aa * bb
            bits = 0
            for n in range(64):
                bit = 1 << n
                bits += bool(bit & mul)
            result[count, :] = aa, bb, bits
            count += 1
            bb += b.step
        aa += a.step
    return result


ctx.compute()

bits = calc_bits(ctx.a.value, ctx.b.value)
print(bits[:3])
print(bits[-3:])

ctx.calc_bits = calc_bits
ctx.calc_bits.a = ctx.a
ctx.calc_bits.pins.a.celltype = "silk"
ctx.calc_bits.b = ctx.b
ctx.calc_bits.pins.b.celltype = "silk"
ctx.bits = ctx.calc_bits
ctx.bits.celltype = "mixed"
ctx.compute()

bits = ctx.bits.value
print(bits[:3])
print(bits[-3:])

def gen_datatable(bits):
    import itables
    itables.to_html = itables.javascript._datatables_repr_
    import pandas as pd
    df = pd.DataFrame(data=bits, columns=["Factor A", "Factor B", "Bits of A*B"])
    columnDefs = [
        {'width': '70px', 'targets': "_all"}, 
        {'className': 'dt-center', 'targets': "_all"}
    ]
    tableId = 'ad9c9d8a-61c4-415b-a1ac-ba60e64c4d81'  # must be different for every table
    return itables.to_html(df, columnDefs=columnDefs, tableId=tableId)
    
datatable = gen_datatable(bits)
print(datatable[:100])
print()
print(datatable[-100:])
ctx.gen_datatable = gen_datatable
ctx.gen_datatable.bits = ctx.bits
ctx.datatable = ctx.gen_datatable
ctx.datatable.celltype = "text"
ctx.datatable.mimetype = "html"
ctx.datatable.share()
ctx.compute()

ctx.html = Cell("text").mount("datatables-dynamic.html", authority="file").share("index.html")
ctx.html.mimetype="html"
ctx.js = Cell("text").mount("datatables-dynamic.js", authority="file").share("index.js")
ctx.js.mimetype="js"

# Get Seamless Javascript client from the Seamless distribution
import os, seamless
seamless_dir = os.path.dirname(seamless.__file__)
c = ctx.seamless_client = Cell()
c.celltype = "text"
c.set(open(seamless_dir + "/js/seamless-client.js").read())
c.mimetype = "text/javascript"
c.share("seamless-client.js")

from itables.javascript import read_package_file
eval_functions_js = read_package_file('javascript', 'eval_functions.js') # from itables itself
eval_functions_js = """
// From the itables project: Copyright (c) 2019 Marc Wouts, MIT License
// https://github.com/mwouts/itables/blob/master/itables/javascript/eval_functions.js
""" + eval_functions_js
ctx.eval_functions_js = eval_functions_js
ctx.eval_functions_js.share("eval_functions.js")
ctx.eval_functions_js.celltype = "text"
ctx.eval_functions_js.mimetype="js"
ctx.compute()

ctx.save_graph("datatables.seamless")
ctx.save_zip("datatables.zip")

print("""datatables.seamless and datatables.zip generated.
You can open these using the datatables.ipynb Jupyter notebook.
You can serve it dynamically using:
seamless-serve-graph-interactive \\
    datatables.seamless \\
    datatables.zip
""")


from jinja2 import Template
with open("datatables-static.jinja") as f:
    template = Template(f.read())
static_html=template.render(eval_functions=eval_functions_js, datatable=datatable)
with open("datatables-static.html", "w") as f:
    f.write(static_html)

