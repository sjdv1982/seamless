from collections import OrderedDict
from seamless import macro, cell, reactor

@macro(OrderedDict((
  ("template_definition", "json"),
  ("output_type", {"type": "dtype", "default": ("text", "html")}),
)))
def templateer(ctx, template_definition, output_type):
    from seamless import cell, reactor
    templates = template_definition["templates"]
    assert isinstance(templates, list)
    environment = template_definition["environment"]
    ed_params = {}
    for t in templates:
        assert t not in ed_params, t
        ed_params[t] = {"pin": "input", "dtype": "text"}
    for k,v in environment.items():
        assert k not in ed_params, k
        ed_params[k] = {"pin": "input", "dtype": v}
    ed_params["TEMPLATE_DEFINITION"] = {"pin": "input", "dtype": "json"}
    ed_params["RESULT"] = {"pin": "output", "dtype": output_type}
    ctx.rc = reactor(ed_params)
    ctx.rc.TEMPLATE_DEFINITION.cell().set(template_definition)
    ctx.rc.code_start.cell().fromfile("cell-templateer.py")
    ctx.rc.code_update.cell().set("make_template()")
    ctx.rc.code_stop.cell().set("")
    ctx.export(ctx.rc)
