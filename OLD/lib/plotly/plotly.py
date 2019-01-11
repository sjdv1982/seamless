from seamless import macro

@macro({"dynamic_html":{"type": "bool", "default": False},
        "mode": {"type": "str", "default": "manual"}}
    )
def plotly(ctx, *, dynamic_html, mode):
    from seamless import context, cell, transformer
    from seamless.lib.templateer import templateer
    from seamless.core.worker import \
      ExportedInputPin, ExportedOutputPin

    assert mode in ("nx", "nxy", "manual"), mode
    data_dtype = "json" if mode == "manual" else "text" #csv

    # Subcontexts
    ctx.values = context()
    ctx.templates = context()
    ctx.params = context()
    ctx.code = context()

    # Static HTML output
    ctx.values.html = cell(("text", "html"))
    ctx.html = ExportedOutputPin(ctx.values.html)

    # Templates
    ctx.templates.html_head_body = cell(("text", "html"))\
      .fromfile("template-html-head-body.jinja")
    ctx.templates.head = cell("text")\
      .fromfile("template-head.jinja")
    ctx.templates.body = cell("text")\
      .fromfile("template-body.jinja")
    ctx.templates.body_dynamic = cell("text")\
      .fromfile("template-body-dynamic.jinja")

    # Values: here is where all authoritative state goes
    ctx.values.title = cell("str").set("Seamless Plotly")
    ctx.values.data = cell(data_dtype)
    ctx.values.attrib = cell("json")
    ctx.values.layout = cell("json")
    ctx.values.config = cell("json").set({})
    ctx.values.width = cell("int").set(500)
    ctx.values.height = cell("int").set(500)
    ctx.values.divname = cell("str").set("plotlydiv")

    # Input pins
    ctx.title = ExportedInputPin(ctx.values.title)
    ctx.data = ExportedInputPin(ctx.values.data)
    ctx.attrib = ExportedInputPin(ctx.values.attrib)
    ctx.layout = ExportedInputPin(ctx.values.layout)
    ctx.config = ExportedInputPin(ctx.values.config)

    # Static HTML: templateer_static
    params_static =  {"environment": {"title": "str",
                               "divname": "str",
                               "width": "int",
                               "height": "int",
                               "plotly_data": "json",
                               "layout": "json",
                               "config": "json",
                              },
                "templates": ["body", "head", "head_body"],
                "result": "head_body"}
    ctx.params.templateer_static = cell("json").set(params_static)
    ctx.templateer_static = templateer(ctx.params.templateer_static)
    ctx.values.height.connect(ctx.templateer_static.height)
    ctx.values.width.connect(ctx.templateer_static.width)
    ctx.values.divname.connect(ctx.templateer_static.divname)
    ctx.values.config.connect(ctx.templateer_static.config)
    ctx.values.layout.connect(ctx.templateer_static.layout)
    ctx.values.title.connect(ctx.templateer_static.title)
    ctx.templates.body.connect(ctx.templateer_static.body)
    ctx.templates.head.connect(ctx.templateer_static.head)
    ctx.templates.html_head_body.connect(ctx.templateer_static.head_body)
    ctx.templateer_static.RESULT.connect(ctx.values.html)

    #plotly_data temporary
    ctx.temp_plotly_data = cell("json")
    ctx.temp_plotly_data.connect(ctx.templateer_static.plotly_data)

    # Data integrator
    ctx.integrate_data = transformer({
        "data": {"pin": "input", "dtype": "json"},
        "attrib": {"pin": "input", "dtype": "json"},
        "plotly_data": {"pin": "output", "dtype": "json"},
    })
    ctx.code.integrate_data = cell(("text", "code","python"))\
      .fromfile("cell-integrate-data.py")
    ctx.code.integrate_data.connect(ctx.integrate_data.code)
    ctx.values.attrib.connect(ctx.integrate_data.attrib)
    ctx.integrate_data.plotly_data.connect(ctx.temp_plotly_data)


    if mode != "manual":
        #loaded_data temporary
        ctx.temp_loaded_data = cell("json")
        ctx.temp_loaded_data.connect(ctx.integrate_data.data)

        # Pandas data loader
        ctx.load_data = transformer({
            "csv": {"pin": "input", "dtype": "text"},
            "data": {"pin": "output", "dtype": "json"},
        })
        c = ctx.code.load_data = cell(("text", "code","python"))
        if mode == "nxy":
            c.fromfile("cell-load-data-nxy.py")
        elif mode == "nx":
            c.fromfile("cell-load-data-nx.py")
        ctx.code.load_data.connect(ctx.load_data.code)
        ctx.values.data.connect(ctx.load_data.csv)
        ctx.load_data.data.connect(ctx.temp_loaded_data)
    else:
        ctx.values.data.connect(ctx.integrate_data.data)

    if not dynamic_html:
        return

    from seamless.lib.dynamic_html import dynamic_html

    # Dynamic HTML output
    ctx.values.dynamic_html = cell(("text", "html"))
    ctx.dynamic_html = ExportedOutputPin(ctx.values.dynamic_html)

    # Dynamic HTML: templateer_dynamic
    ctx.params.templateer_dynamic = cell("json")
    params =  {"environment": {"title": "text",
                           "divname": "text",
                           "width": "int",
                           "height": "int",
                           "dynamic_html": ("text","html")
                          },
            "templates": ["body", "head", "head_body"],
            "result": "head_body"}
    ctx.params.templateer_dynamic.set(params)
    ctx.templateer_dynamic = templateer(ctx.params.templateer_dynamic)

    ctx.values.height.connect(ctx.templateer_dynamic.height)
    ctx.values.width.connect(ctx.templateer_dynamic.width)
    ctx.values.divname.connect(ctx.templateer_dynamic.divname)
    ctx.values.title.connect(ctx.templateer_dynamic.title)
    ctx.templates.body_dynamic.connect(ctx.templateer_dynamic.body)
    ctx.templates.head.connect(ctx.templateer_dynamic.head)
    ctx.templates.html_head_body.connect(ctx.templateer_dynamic.head_body)
    ctx.templateer_dynamic.RESULT.connect(ctx.values.dynamic_html)

    # Dynamic HTML maker
    # TODO: more efficient plot regeneration
    ctx.params.dynamic_html_maker = cell("json")
    dynamic_html_params = {
        "divname": {"type": "var", "dtype": "str"},
        "plotly_data": {"type": "var", "dtype": "json", "evals":["make_plot"]},
        #"data": {"type": "var", "dtype": "json", "evals":["update_data"]},
        #"attrib": {"type": "var", "dtype": "json", "evals":["update_attrib"]},
        #"layout": {"type": "var", "dtype": "json", "evals":["update_layout"]},
        "data": {"type": "var", "dtype": "json"},
        "attrib": {"type": "var", "dtype": "json", "evals":["make_plot"]},
        "layout": {"type": "var", "dtype": "json", "evals":["make_plot"]},

        "config": {"type": "var", "dtype": "json", "evals":["make_plot"]},
        "update_data": {"type": "eval", "on_start": False},
        "update_attrib": {"type": "eval", "on_start": False},
        "update_layout": {"type": "eval", "on_start": False},
        "make_plot": {"type": "eval", "on_start": True},
    }
    ctx.params.dynamic_html_maker.set(dynamic_html_params)
    ctx.dynamic_html_maker = dynamic_html(ctx.params.dynamic_html_maker)
    ctx.dynamic_html_maker.dynamic_html.cell().connect(
        ctx.templateer_dynamic.dynamic_html
    )

    ctx.temp_plotly_data.connect(ctx.dynamic_html_maker.plotly_data)
    if mode == "manual":
        ctx.values.data.connect(ctx.dynamic_html_maker.data)
    else:
        ctx.temp_loaded_data.connect(ctx.dynamic_html_maker.data)
    ctx.values.attrib.connect(ctx.dynamic_html_maker.attrib)
    ctx.values.config.connect(ctx.dynamic_html_maker.config)
    ctx.values.layout.connect(ctx.dynamic_html_maker.layout)

    ctx.dynamic_html_maker.make_plot.cell().set("""
Plotly.newPlot(divname, plotly_data, layout, config);
    """)

    ctx.dynamic_html_maker.update_data.cell().set("""
var i, ii, subdata, update, attribname;
for (i = 0; i < plotly_data.length; i++) {
    subdata = data[i];
    update = {};
    for (var attribname in subdata) {
        update[attribname] = [subdata[attribname]];
    }
    /*if (i==0) {
        x = document.getElementById("echo");
        x.innerHTML = "<pre>" + JSON.stringify(update) + "</pre>";
    }*/
    Plotly.restyle(divname, update, [i]);
}
    """)
    ctx.dynamic_html_maker.update_attrib.cell().set("""
var i;
for (i = 0; i < plotly_data.length; i++) {
    Plotly.restyle(divname, attrib[i], [i]);
}
    """)
    ctx.dynamic_html_maker.update_layout.cell().set("""
Plotly.relayout(divname, layout);
    """)

    ctx.values.divname.connect(ctx.dynamic_html_maker.divname)
