# inputs:
# - webform
# - components
# - seed

import os
from jinja2 import Template
import random
import json

def ident():
    return "id-%d" % random.randint(1,10000)

encodings = ["text", "json"]
defaults = {
    "int": 0,
    "float": 0.0,
    "str": "",
    "plain": {},
    "text": "",
    "bool": False,
}

result = {}

random.seed(seed)
COMPONENTS = ""
WATCHERS = ""
SEAMLESS_READ_CELLS = {k:[] for k in encodings}
SEAMLESS_WRITE_CELLS = {k:[] for k in encodings}
VUE_DATA = {}

order = webform.get("order", [])
for cell in webform["cells"]:
    if cell not in order:
        order.append(cell)

for cell in order:
    config = webform["cells"][cell]
    default = defaults[config["celltype"]]
    VUE_DATA[cell] = default
    if "share" in config:
        par = config["share"]
        encoding = par["encoding"]
        if par.get("read"):
            SEAMLESS_READ_CELLS[encoding].append(cell)
        if par.get("write"):
            SEAMLESS_WRITE_CELLS[encoding].append(cell)
            code = """{cell}: function (value) {{
    seamless_update("{cell}", value, "{encoding}")
    }},""".format(cell=cell, encoding=encoding)
            WATCHERS += code + "\n    "
    if "component" not in config:
        continue
    component = config["component"]
    par = config.get("params",{}).copy()
    for n in range(10):
        par["ID%d" % (n+1)] = ident()
    par["CELL"] = cell

    component_template = components[component + ".jinja.html"]
    template = Template(component_template)
    html = template.render(**par)
    COMPONENTS += html + "\n"

component_template = components["INDEX.jinja.html"]
template = Template(component_template)
par = webform["index"]
index_html = template.render(COMPONENTS=COMPONENTS, **par)
result["index.html"] = index_html

component_template = components["INDEX.jinja.js"]
template = Template(component_template)
index_js = template.render(
    SEAMLESS_READ_CELLS=json.dumps(SEAMLESS_READ_CELLS, indent=2),
    SEAMLESS_WRITE_CELLS=json.dumps(SEAMLESS_WRITE_CELLS, indent=2),
    VUE_DATA=json.dumps(VUE_DATA, indent=2).replace("\n", "\n    "),
    WATCHERS=WATCHERS
)
result["index.js"] = index_js
