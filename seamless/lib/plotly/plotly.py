from seamless import macro

@macro
def plotly(ctx):
    from seamless import context, cell, transformer
    from seamless.lib.templateer import templateer
    from seamless.core.worker import \
      ExportedInputPin, ExportedOutputPin

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
    ctx.templates.body = cell("text")\
      .fromfile("template-body.jinja")
    ctx.templates.head = cell("text")\
      .fromfile("template-head.jinja")

    # Values: here is where all authoritative state goes
    ctx.values.title = cell("str").set("Seamless Plotly")
    ctx.values.data = cell("text") #csv
    ctx.values.attrib = cell("json")
    ctx.values.layout = cell("json")
    ctx.values.config = cell("json").set({})
    ctx.values.width = cell("int").set(500)
    ctx.values.height = cell("int").set(500)
    ctx.values.divname = cell("str").set("plotlydiv")

    # Input pins
    ctx.title = ExportedInputPin(ctx.values.title) 
    ctx.data = ExportedInputPin(ctx.values.data) #csv
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

    #loaded_data temporary
    ctx.temp_loaded_data = cell("json")
    ctx.temp_loaded_data.connect(ctx.integrate_data.data)

    # Pandas data loader
    ctx.load_data_nxy = transformer({
        "csv": {"pin": "input", "dtype": "text"},
        "data": {"pin": "output", "dtype": "json"},
    })
    ctx.code.load_data_nxy = cell(("text", "code","python"))\
      .fromfile("cell-load-data-nxy.py")
    ctx.code.load_data_nxy.connect(ctx.load_data_nxy.code)
    ctx.values.data.connect(ctx.load_data_nxy.csv)
    ctx.load_data_nxy.data.connect(ctx.temp_loaded_data)
