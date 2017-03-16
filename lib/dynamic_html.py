from seamless import cell, macro

@macro("json")
def dynamic_html(ctx, params):
    from seamless import editor
    from collections import OrderedDict
    params2 = { "vars": OrderedDict(),
                "html": OrderedDict(),
                "evals": OrderedDict()
              }
    ed_params = {
        "DYNAMIC_HTML_PARAMS": {
            "pin": "input",
            "dtype": "json"
        },
        "DYNAMIC_HTML_TEMPLATE": {
            "pin": "input",
            "dtype": "text"
        },
        "dynamic_html": {
            "pin": "output",
            "dtype": ("text", "html")
        }
    }
    assert "dynamic_html" not in params
    for k,v in params.items():
        assert isinstance(v,dict), k
        ed_param = {"pin": "input"}
        type_ = v["type"]
        assert type_ in ("var", "html", "eval"), type_
        if type_ == "var":
            dtype = v.get("dtype")
            evals = v.get("evals", [])
            var = v.get("var", k)
            params2["vars"][k] = (var, evals)
            ed_param["dtype"] = dtype
        elif type_ == "html":
            id_ = v.get("id", k)
            params2["html"][k] = id_
            ed_param["dtype"] = ("text", "html")
        else: #type_ = "eval"
            on_start = v.get("on_start", None)
            params2["evals"][k] = on_start
            ed_param["dtype"] = "text"
        ed_params[k] = ed_param
    for k,v in params2["vars"].items():
        var, evals = v
        for e in evals:
            assert e in params2["evals"], (k, e, list(params2["evals"].keys()))
    ed = ctx.ed = editor(ed_params)
    ed.code_start.cell().fromfile("cell-dynamic-html-start.py")
    ed.code_update.cell().set("update(on_start=False)")
    ed.code_stop.cell().set("")
    ed.DYNAMIC_HTML_PARAMS.cell().set(params2)
    ed.DYNAMIC_HTML_TEMPLATE.cell().fromfile("dynamic-html.jinja")
    ctx.export(ed)
