""" Build workflow graph for the datatables example. 

While the workflow graph is live, it is a Seamless context (ctx)
It is saved in JSON format (.seamless extension)
The .seamless graph file contains only checksums; 
 the corresponding value buffers are in a zip file.

The datatable is originally computed as a three-column Numpy array.
The first and second columns are elements from A and B.
A and B are integer sequences whose values are defined by 
 the "first", "step" and "length" parameters.
These parameters are controlled via Seamless cells that are shared over HTTP (REST).
The third column is the number of bits of A*B.

During visualization, the datatable Numpy array is first converted to Pandas, 
and then to HTML using itables.
"""

from seamless.highlevel import Context, Cell
ctx = Context()

# Create "first", "step", "length" parameters for sequence A
ctx.a_first = Cell("int").set(5)
ctx.a_first.share(readonly=False)   # Because of .share, the cell value can be read via HTTP 
                                    #  (e.g. in the browser)
                                    # Because of readonly=False, this cell can also be set via HTTP 
                                    #  (PUT request)
ctx.a_step = Cell("int").set(3)
ctx.a_step.share(readonly=False)
ctx.a_length = Cell("int").set(5)
ctx.a_length.share(readonly=False)

# Create cell A that holds all three parameters
ctx.a = Cell()
ctx.a.first = ctx.a_first
ctx.a.step = ctx.a_step
ctx.a.length = ctx.a_length

###########################################################

# Define a JSON Schema for A (and B), that will be written 
# to "sequence_schema.json"
# See https://json-schema.org/ for more details

ctx.schema = Cell("plain")
ctx.translate()

# We have three ways of defining the JSON Schema in Seamless:

# Method 1. Linking to a JSON Schema file that we can edit by hand:
ctx.link(ctx.a.schema, ctx.schema)
ctx.schema.mount("sequence_schema.json")
ctx.compute()

# Method 2. Setting properties by example. 
# Seamless can do some type inference.
# The code below will define "first", "step" and "length" as integers.
example = ctx.a.example
example.first = 0
example.step = 0
example.length = 0

# Method 3. Defining the schema directly, programmatically 
props = ctx.a.schema.properties
props.step.minimum = 1
props.first.minimum = 1
props.length.minimum = 1

###########################################################

# Create "first", "step", "length" parameters for sequence B
ctx.b_first = Cell("int").set(8)
ctx.b_first.share(readonly=False)
ctx.b_step = Cell("int").set(1)
ctx.b_step.share(readonly=False)
ctx.b_length = Cell("int").set(4)
ctx.b_length.share(readonly=False)

# Create cell B that holds all three parameters
ctx.b = Cell()
ctx.translate()
ctx.b.first = ctx.b_first
ctx.b.step = ctx.b_step
ctx.b.length = ctx.b_length

# Link "sequence_schema.json" also to cell B
ctx.link(ctx.b.schema, ctx.schema)

###########################################################

# The actual calculation. 
# Each combination of each element from A and B is multiplied
#  and the number of bits is determined.
# The result contains a Numpy array of (element A, element B, number of bits)
#
# Note that we must do all code imports *inside* the function,
#  since no variables from the main script are accessible.
def calc_bits(a, b):  # def calc_bits(a:silk.Silk, b:silk.Silk) -> np.ndarray
    import numpy as np
    result = np.zeros((a.length*b.length, 3),int)
    count = 0
    aa = a.first.unsilk    
    for _ in range(a.length):
        bb = b.first.unsilk
        for _ in range(b.length):
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

# Run the function outside of Seamless
bits = calc_bits(ctx.a.value, ctx.b.value)
print(bits[:3])
print(bits[-3:])

# Add it to the workflow
ctx.calc_bits = calc_bits

ctx.calc_bits.a = ctx.a
ctx.calc_bits.pins.a.celltype = "silk"  
# "a" inside the transformer has now the same type and value as ctx.a.value

ctx.calc_bits.b = ctx.b
ctx.calc_bits.pins.b.celltype = "silk"  
# "b" inside the transformer has now the same type and value as ctx.b.value

ctx.bits = ctx.calc_bits
ctx.bits.celltype = "binary"
ctx.compute()

bits = ctx.bits.value
print(bits[:3])
print(bits[-3:])

###########################################################

# Now, to generate the datatable:
#  First generate a Pandas DataFrame
#  Then, save it as HTML using itables
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

# Run the function outside of Seamless    
datatable = gen_datatable(bits)
print(datatable[:100])
print()
print(datatable[-100:])

# Add it to the workflow
ctx.gen_datatable = gen_datatable
ctx.gen_datatable.bits = ctx.bits
ctx.datatable = ctx.gen_datatable

# Define it as a Seamless cell, shared over HTTP (read-only)
# as http://<server>/ctx/datatable
ctx.datatable.celltype = "text"
ctx.datatable.mimetype = "html"
ctx.datatable.share()
ctx.compute()

# We will need eval_functions.js from itables
from itables.javascript import read_package_file
eval_functions_js = read_package_file('javascript', 'eval_functions.js') # from itables itself
eval_functions_js = """
// From the itables project: Copyright (c) 2019 Marc Wouts, MIT License
// https://github.com/mwouts/itables/blob/master/itables/javascript/eval_functions.js
""" + eval_functions_js

# Write the initial value of the datatable into static HTML
from jinja2 import Template
with open("datatables-static.jinja") as f:
    template = Template(f.read())
static_html=template.render(eval_functions=eval_functions_js, datatable=datatable)
with open("datatables-static.html", "w") as f:
    f.write(static_html)

# Get Seamless Javascript client from the Seamless distribution
#  The function of this client is to bidirectionally synchronize the ctx object 
#    between the browser's Javascript variable space 
#    and the Seamless server, for shared cells that change value.
#   In our case, these cells are ctx.datatable and ctx.a_step, ctx.b_step, etc.
import os, seamless
seamless_dir = os.path.dirname(seamless.__file__)
c = ctx.seamless_client = Cell()
c.celltype = "text"
c.set(open(seamless_dir + "/js/seamless-client.js").read())
c.mimetype = "text/javascript"
c.share("seamless-client.js")

# Now, we will define a dynamic web page that allows us to:
#   (1) edit ctx.a_step, ctx.b_step, etc. in the browser
#   (2) re-display the ctx.datatable HTML as it is regenerated.
#
# (1) happens in line 32-34 of in datatables-dynamic.js:
#   whenever DOM element "b_first" changes, ctx.b_first changes in the browser,
#    which the Seamless client propagates to the server.
# (2) happens in line 16-20. Whenever a new value of ctx.datatable arrives,
#   the HTML is unwrapped and injected into DOM element "datatable".
#
# The web page HTML and JS are *also* put in shared cells, 
#  but they don't need to be bidirectionally synchronized.
#  they just need to be accessible to the browser.
# The web page will be accessible under <server>/ctx/index.html etc.

ctx.html = Cell("text").mount("datatables-dynamic.html", authority="file").share("index.html")
ctx.html.mimetype="html"

ctx.js = Cell("text").mount("datatables-dynamic.js", authority="file").share("index.js")
ctx.js.mimetype="js"

ctx.eval_functions_js = eval_functions_js
ctx.eval_functions_js.share("eval_functions.js")
ctx.eval_functions_js.celltype = "text"
ctx.eval_functions_js.mimetype="js"

ctx.compute()

###########################################################

# Save the graph
ctx.save_graph("datatables.seamless")
ctx.save_zip("datatables.zip")

print("""datatables.seamless and datatables.zip generated.
You can open these using the datatables.ipynb Jupyter notebook.
Alternatively, you can serve it independently using:

seamless-serve-graph \\
    datatables.seamless \\
    datatables.zip
 
or:

seamless-serve-graph \\
    /home/jovyan/seamless-examples/datatables-example/datatables.seamless \\
    /home/jovyan/seamless-examples/datatables-example/datatables.zip

and opening http://localhost:5813 in the browser.
""")
