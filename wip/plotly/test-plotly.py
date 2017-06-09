import seamless
from seamless import context, cell
from seamless.lib.filelink import link
from seamless.lib.gui.browser import browser
from seamless.lib.templateer import templateer
ctx = context()
ctx.links = context()
ctx.templates = context()
ctx.html = cell(("text", "html"))
ctx.links.html = link(ctx.html, "plotdata", "plotly.html")
ctx.browser = browser()
ctx.html.connect(ctx.browser.value)
ctx.templates.html_head_body = cell(("text", "html"))
ctx.links.template_html_head_body = link(
  ctx.templates.html_head_body,
  ".", "template-html-head-body.jinja"
)
ctx.params = context()
ctx.params.templateer_static = cell("cson")
ctx.links.params_templateer_static = link(ctx.params.templateer_static, ".", "params-templateer-static.cson")
params = {"environment": {"head": "text", "body": "text"}, "templates": ["head_body"]}
ctx.params.templateer_static.set(params)
ctx.templateer_static = templateer(ctx.params.templateer_static)
ctx.templateer_static.RESULT.connect(ctx.html)
ctx.temp_body = cell("text")
ctx.temp_head = cell("text")
ctx.links.temp_head = link(ctx.temp_head, "temp", "head.txt")
ctx.links.temp_body = link(ctx.temp_body, "temp", "body.txt")
ctx.temp_head.connect(ctx.templateer_static.head)
ctx.temp_body.connect(ctx.templateer_static.body)
ctx.templates.html_head_body.connect(ctx.templateer_static.head_body)
ctx.title = cell("text")
ctx.templates.head = cell("text")
ctx.links.template_head = link(ctx.templates.head, ".", "template-head.jinja")
ctx.temp_head.disconnect(ctx.templateer_static.head) ###
params =  {"environment": {"title": "text", "body": "text"},
            "templates": ["head", "head_body"],
            "result": "head_body"}
ctx.params.templateer_static.set(params)
del ctx.temp_head
del ctx.links.temp_head
ctx.templates.head.connect(ctx.templateer_static.head)
ctx.title.connect(ctx.templateer_static.title)
ctx.links.title = link(ctx.title, "plotdata", "title.txt")

ctx.tofile("plotly.seamless", backup=False)

ctx.templates.body = cell("text")
ctx.links.template_body = link(ctx.templates.body, ".", "template-body.jinja")
params =  {"environment": {"title": "text",
                           "divname": "str",
                           "width": "int",
                           "height": "int",
                           "plotly_data": "json",
                           "layout": "json",
                           "config": "json",
                          },
            "templates": ["body", "head", "head_body"],
            "result": "head_body"}
ctx.temp_body.disconnect(ctx.templateer_static.body) ###
ctx.params.templateer_static.set(params)
ctx.divname = cell("str").set("plotlydiv")
ctx.divname.connect(ctx.templateer_static.divname)
ctx.templateer_static.width.cell().set(500)
ctx.templateer_static.height.cell().set(500)
ctx.plotly_data = cell("cson")
ctx.links.plotly_data = link(ctx.plotly_data, "plotdata", "plotly_data.cson")
ctx.plotly_layout = cell("cson")
ctx.links.plotly_layout = link(ctx.plotly_layout, "plotdata", "layout.cson")
ctx.plotly_config = cell("cson")
ctx.links.plotly_config = link(ctx.plotly_config, "plotdata", "config.cson")
ctx.plotly_data.connect(ctx.templateer_static.plotly_data)
ctx.plotly_config.connect(ctx.templateer_static.config)
ctx.plotly_layout.connect(ctx.templateer_static.layout)
ctx.templates.body.connect(ctx.templateer_static.body)

from seamless import transformer
ctx.integrate_data = transformer({
    "data": {"pin": "input", "dtype": "json"},
    "attrib": {"pin": "input", "dtype": "json"},
    "plotly_data": {"pin": "output", "dtype": "json"},
})
ctx.code = context()
ctx.code.integrate_data = cell(("text", "code","python"))
ctx.links.code_integrate_data = link(
    ctx.code.integrate_data, ".", "cell-integrate-data.py"
)
ctx.code.integrate_data.connect(ctx.integrate_data.code)
ctx.data = cell("json")
ctx.data.connect(ctx.integrate_data.data)
ctx.links.data = link(ctx.data, "plotdata", "data.json")
ctx.attrib = cell("cson")
ctx.attrib.connect(ctx.integrate_data.attrib)
ctx.links.attrib = link(ctx.attrib, "plotdata", "attrib.cson")
ctx.integrate_data.plotly_data.connect(ctx.plotly_data)

ctx.load_data_nxy = transformer({
    "csv": {"pin": "input", "dtype": "text"},
    "data": {"pin": "output", "dtype": "json"},
})
ctx.code.load_data_nxy = cell(("text", "code","python"))
ctx.code.load_data_nxy.connect(ctx.load_data_nxy.code)
ctx.links.code_load_data_nxy = link(
    ctx.code.load_data_nxy, ".", "cell-load-data-nxy.py"
)
ctx.csv = cell("text")
ctx.links.csv = link(ctx.csv, "plotdata", "data.csv")
ctx.csv.connect(ctx.load_data_nxy.csv)
ctx.load_data_nxy.data.connect(ctx.data)

ctx.html_dynamic = cell(("text", "html"))
ctx.links.html_dynamic = link(ctx.html, "plotdata", "plotly_dynamic.html")
ctx.browser_dynamic = browser()
ctx.html_dynamic.connect(ctx.browser_dynamic.value)

ctx.params.templateer_dynamic = cell("cson")
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
ctx.templateer_dynamic.RESULT.connect(ctx.html_dynamic)
ctx.title.connect(ctx.templateer_dynamic.title)
ctx.divname.connect(ctx.templateer_dynamic.divname)
ctx.templateer_dynamic.width.cell().set(500)
ctx.templateer_dynamic.height.cell().set(500)
ctx.templates.head.connect(ctx.templateer_dynamic.head)
ctx.templates.body_dynamic = cell("text")
ctx.links.template_body_dynamic = link(
    ctx.templates.body_dynamic, ".", "template-body-dynamic.jinja"
)
ctx.templates.body_dynamic.connect(ctx.templateer_dynamic.body)
ctx.templates.html_head_body.connect(ctx.templateer_dynamic.head_body)

print(ctx.templateer_dynamic.ed.editor._pending_inputs)

from seamless.lib.dynamic_html import dynamic_html
ctx.params.dynamic_html = cell("json")
dynamic_html_params = {
    "divname": {"type": "var", "dtype": "str"},
    "plotly_data": {"type": "var", "dtype": "json"},
    "config": {"type": "var", "dtype": "json"},
    "layout": {"type": "var", "dtype": "json"},
    "make_plot": {"type": "eval", "on_start": True},
}
ctx.params.dynamic_html.set(dynamic_html_params)
ctx.dynamic_html_maker = dynamic_html(ctx.params.dynamic_html)
ctx.dynamic_html_maker.dynamic_html.cell().connect(
    ctx.templateer_dynamic.dynamic_html
)
#ctx.divname.connect(ctx.dynamic_html_maker.divname) ###
ctx.plotly_data.connect(ctx.dynamic_html_maker.plotly_data)
ctx.plotly_config.connect(ctx.dynamic_html_maker.config)
ctx.plotly_layout.connect(ctx.dynamic_html_maker.layout)
ctx.dynamic_html_maker.make_plot.cell().set("""
Plotly.newPlot(divname, plotly_data, layout, config);
""")

dynamic_html_params = {
    "divname": {"type": "var", "dtype": "str"},
    "plotly_data": {"type": "var", "dtype": "json"},
    "data": {"type": "var", "dtype": "json", "evals":["update_data"]},
    "attrib": {"type": "var", "dtype": "json", "evals":["update_attrib"]},
    "config": {"type": "var", "dtype": "json", "evals":["make_plot"]},
    "layout": {"type": "var", "dtype": "json", "evals":["update_layout"]},
    "update_data": {"type": "eval", "on_start": False},
    "update_attrib": {"type": "eval", "on_start": False},
    "update_layout": {"type": "eval", "on_start": False},
    "make_plot": {"type": "eval", "on_start": True},
}
ctx.params.dynamic_html.set(dynamic_html_params)
ctx.attrib.connect(ctx.dynamic_html_maker.attrib)
ctx.data.connect(ctx.dynamic_html_maker.data)
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

ctx.divname.connect(ctx.dynamic_html_maker.divname) ###
