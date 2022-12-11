# For the docstring, do `webctx.generate_webpage?` in IPython

# inputs:
# - webform
# - components
# - seed

import os
from jinja2 import Template
import random
import json

idents = set()
def ident():
    while 1:
        result = "id-%d" % random.randint(1,10000)
        if result not in idents:
            idents.add(result)
            return result

encodings = ["text", "json"]

# Rewrite the webform, modifying the names of cells/transformers
#  by replacing "/" with "__".
# This is necessary to avoid problems with Vue.

for dic in (webform["cells"], webform.get("extra_cells", {}), webform["transformers"]):
    for name in list(dic.keys()):
        if name.find("/") > -1:
            v = dic.pop(name)
            name2 = name.replace("/", "__")
            dic[name2] = v
for comp in webform["extra_components"]:
    if "cell" in comp:
        comp["cell"] = comp["cell"].replace("/", "__")
    if "cells" in comp:
        for k, v in comp["cells"].items():
            comp["cells"][k] = v.replace("/", "__")
    
# / rewrite

result = {}
watchers = {}

random.seed(seed)
COMPONENT_JS = ""
COMPONENTS = ""
WATCHERS = ""
SEAMLESS_READ_PATHS = {k:[] for k in encodings}
SEAMLESS_WRITE_PATHS = {k:[] for k in encodings}
SEAMLESS_AUTO_READ_PATHS = []
SEAMLESS_PATH_TO_CELL = {}
INIT_CODE = ""
HEAD_HTML = ""
BODY_HTML = ""
VUE_DATA = {}

extra_components = {}

order = webform.get("order", [])
for cell in webform["cells"]:
    cell2 = cell.replace("__", "/")
    if cell2 not in order:
        order.append(cell2)
for tf in webform["transformers"]:
    tf2 = tf.replace("__", "/")
    if tf2 not in order:
        order.append(tf2)
print("ORDER", order)

used_extra_cells = set()
for extra_component in webform.get("extra_components", []):
    id = extra_component.get("id", None)
    if id is None:
        raise ValueError("All extra components must have a field 'id'")
    if id in webform["cells"]:
        raise ValueError("Extra component cannot have id '{}': cell with that name already exists".format(id))
    cell = extra_component.get("cell", None)
    if cell is not None:
        if cell not in webform["cells"]:
            raise ValueError("Extra component cannot have cell '{}': no cell with that name exists".format(cell))
    cells = extra_component.get("cells", {})
    for k,cell in cells.items():
        if cell in webform["cells"]:
            pass
        elif cell in webform.get("extra_cells", {}):
            used_extra_cells.add(cell)
        elif cell in webform.get("webcells", {}):
            pass 
        else:
            raise ValueError("Extra component cannot have cell '{}': no cell, extra cell or webcell with that name exists".format(cell))
    extra_components[id] = extra_component
    if id not in order:
        order.append(id)

used_components = set()
has_file = []

for cell in used_extra_cells:
    order.append(cell)

for cell_or_tf_or_id in order:
    if cell_or_tf_or_id in extra_components:
        id = cell_or_tf_or_id
        extra_component = extra_components[id]
        if "component" not in extra_component:
            continue
        component = extra_component["component"]
        if component == "":
            continue
        par = extra_component.get("params",{}).copy()
        cell = extra_component.get("cell")
        if cell is not None:
            for n in range(10):
                par["ID%d" % (n+1)] = ident()
            par["CELL"] = cell
        cells = extra_component.get("cells")
        if cells is not None:
            par["CELLS"] = cells
        par["ID"] = id

        component_template = components[component + ".jinja.html"]
        template = Template(component_template)
        html = template.render(**par)
        COMPONENTS += html + "\n"

        used_components.add(component)        

        component_params = components.get(component + ".json")
        if component_params is not None:
            component_params = json.loads(component_params)
            if component_params.get("file"):
                if cell not in has_file:
                    has_file.append(cell)

        component_watch = components.get(component + ".watch.jinja")
        if component_watch is not None:
            template = Template(component_watch)
            watch_expr_data = template.render(**par)
            for watch_expr in watch_expr_data.splitlines():
                watch_expr = watch_expr.strip()
                if watch_expr.startswith("#"):
                    continue
                try:
                    pre, func = watch_expr.split("=>")
                    func = func.strip()
                    wvars = [wvar.strip() for wvar in pre.split(",")]
                    wvars2 = []
                    wvars3 = []
                    for wvar in wvars:
                        if wvar.startswith("@"):
                            wvars2.append(wvar[1:])
                        elif wvar.startswith('"'):
                            wvars2.append(wvar)
                        else:
                            wvars2.append("this." + wvar)
                            wvars3.append(wvar)
                    code = "function(){{ {}({}) }}".format(func, ",".join(wvars2))
                    for wvar in wvars3:
                        wkey = wvar
                        if wkey not in watchers:
                            watchers[wkey] = []
                        watchers[wkey].append(code)

                except Exception:
                    import traceback
                    traceback.print_exc()
                    continue

        if component_watch is not None:
            template = Template(component_watch)
            watch_expr_data = template.render(**par)

        component_init_js = components.get(component + ".INIT.js")
        if component_init_js is not None:
            INIT_CODE += Template(component_init_js).render(**par) + "\n"

        continue
    elif cell_or_tf_or_id in webform["transformers"]:
        tf = cell_or_tf_or_id
        transformer = webform["transformers"][tf]
        component = transformer["component"]
        if component == "":
            continue
        par = transformer.get("params",{}).copy()
        for n in range(10):
            par["ID%d" % (n+1)] = ident()
        par["TRANSFORMER"] = tf

        component_template = components[component + ".jinja.html"]
        template = Template(component_template)
        html = template.render(**par)
        COMPONENTS += html + "\n"

        used_components.add(component)        
        continue

    cell = cell_or_tf_or_id
    cell = cell.replace("/", "__") 
    if cell in used_extra_cells and cell not in webform["cells"]:
        config = webform["extra_cells"][cell]
    elif cell in webform.get("webcells", {}):
        continue
    else:
        config = webform["cells"][cell]
    webdefault = config["webdefault"]
    path = config.get("path", cell).replace("/", "__")
    if path != cell:
        SEAMLESS_PATH_TO_CELL[path] = cell
    if "share" in config:
        par = config["share"]
        encoding = par["encoding"]
        if par.get("auto_read"):
            SEAMLESS_AUTO_READ_PATHS.append(path)
        if par.get("read"):
            SEAMLESS_READ_PATHS[encoding].append(path)
        if par.get("write"):
            SEAMLESS_WRITE_PATHS[encoding].append(path)
            code = """function (value) {{
      seamless_update("{path}", value, "{encoding}")
    }}""".format(path=path, encoding=encoding)
            wkey = cell + ".value"
            if wkey not in watchers:
                watchers[wkey] = []
            watchers[wkey].append(code)
            '''
            code = """"{cell}.value": function (value) {{
      seamless_update("{path}", value, "{encoding}")
    }},""".format(cell=cell, path=path, encoding=encoding)
            WATCHERS += code + "\n    "
            '''
    VUE_DATA[cell] = {
        "checksum": None,
        "value": webdefault
    }
    if "component" not in config:
        continue
    component = config["component"]
    if component == "":
        continue
    used_components.add(component)
    par = config.get("params",{}).copy()
    for n in range(10):
        par["ID%d" % (n+1)] = ident()
    par["CELL"] = cell

    component_template = components[component + ".jinja.html"]
    template = Template(component_template)
    html = template.render(**par)
    COMPONENTS += html + "\n"
    
    component_params = components.get(component + ".json")
    if component_params is not None:
        component_params = json.loads(component_params)
        if component_params.get("file"):
            if cell not in has_file:
                has_file.append(cell)

for component in used_components:
    component_js = components.get(component + ".js")
    if component_js is not None:
        COMPONENT_JS += component_js + "\n"
        
    component_head_html = components.get(component + ".HEAD.html")
    if component_head_html is not None:
        HEAD_HTML += component_head_html

    component_body_html = components.get(component + ".BODY.html")
    if component_body_html is not None:
        BODY_HTML += component_body_html

for cell in has_file:
    code = """function (file) {{
      this.METHOD_file_upload("{cell}", file)
    }}""".format(cell=cell)
    wkey = cell + ".file"
    if wkey not in watchers:
        watchers[wkey] = []
    watchers[wkey].append(code)
    '''
    code = """"{cell}.file": function (file) {{
      this.METHOD_file_upload("{cell}", file)
    }},""".format(cell=cell)
    WATCHERS += code + "\n    "
    '''

for cell, default in webform.get("webcells", {}).items():
    VUE_DATA[cell] = {
        "value": default
    }

component_template = components["INDEX.jinja.html"]
template = Template(component_template)
par = webform["index"]
index_html = template.render(HEAD=HEAD_HTML, BODY=BODY_HTML, COMPONENTS=COMPONENTS, **par)
result["index.html"] = index_html

component_template = components["INDEX.jinja.js"]
template = Template(component_template)
for wkey, wvalue in watchers.items():
    if len(wvalue) == 1:
        witem = wvalue[0]
    else:
        witem = "["
        for wvv in wvalue:
            witem += wvv + ",\n    "
        witem = witem + "]"
    WATCHERS += '"{}": {},'.format(wkey, witem) + "\n    "
index_js = template.render(
    COMPONENT_JS=COMPONENT_JS,
    SEAMLESS_READ_PATHS=json.dumps(SEAMLESS_READ_PATHS, indent=2),
    SEAMLESS_WRITE_PATHS=json.dumps(SEAMLESS_WRITE_PATHS, indent=2),
    SEAMLESS_AUTO_READ_PATHS=json.dumps(SEAMLESS_AUTO_READ_PATHS, indent=2),
    SEAMLESS_PATH_TO_CELL=json.dumps(SEAMLESS_PATH_TO_CELL, indent=2),
    INIT_CODE=INIT_CODE,
    VUE_DATA=json.dumps(VUE_DATA, indent=2).replace("\n", "\n      "),
    WATCHERS=WATCHERS.rstrip()
)
result["index.js"] = index_js
