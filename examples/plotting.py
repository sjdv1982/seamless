from seamless.cell import transformer, pythoncell, macro, composite

@macro("__main__.plotter")
def plotter(arraynames,plotformat="svg"):
    assert plotformat in ("png", "pdf", "ps", "eps", "svg"), plotformat
    ret = composite()

    f = ("markup", "svg") if plotformat == "svg" else plotformat
    transformer_params = {
        "import_" : {
            "pin": "inputpin",
            "type" : "codeblock",
            "order": 0,
        },
        "code" : {
            "pin": "inputpin",
            "type" : "codeblock",
            "order": 1,
        },
        "plot" : {
            "pin": "inputpin",
            "type" : "codefunction",
        },
        "output" : {
            "pin": "outputpin",
            "format": f,
        }
    }
    for arrayname in arraynames:
        assert arrayname not in transformer_params, arrayname
        transformer_params[arrayname] = {
            "pin": "inputpin",
            "type": "buffer",
            "subtype": "numpy",
        }
    t = transformer(transformer_params)
    c_import = pythoncell(value = """
import matplotlib.pyplot as plt
plt.close('all')
""")
    c_plot = pythoncell(value = """
import cStringIO as StringIO
f = StringIO.StringIO()
plt.savefig(f, format='{plotformat}')
return f
""".format(plotformat=plotformat))
    c_import.connect(t.import_)
    c_plot.connect(t.plot)
    ret._c_import = c_import
    ret._c_plot = c_plot
    ret._t = t
    ret.declare_pins(t) #declare all unconnected pins of t as pins of ret
    return ret

if __name__ == "__main__":

    import numpy as np
    t = np.arange(0.0, 2.0, 0.01)
    s = np.sin(2*np.pi*t)
    plotcode = """
plt.plot(t, s)
plt.xlabel('time (s)')
plt.ylabel('voltage (mV)')
plt.title('About as simple as it gets, folks')
plt.grid(True)
"""

    import seamless
    seamless.register()
    from seamless.cell import cell, pythoncell, buffercell
    from seamless.gui import svg_renderer

    c_t = buffercell(value = t)
    c_s = buffercell(value = s)
    c_plotcode = pythoncell(value = plotcode)

    my_plotter = plotter(arraynames = ["t", "s"])
    c_t.connect(my_plotter.t)
    c_s.connect(my_plotter.s)
    c_plotcode.connect(my_plotter.code)

    c_output = cell(type=("markup", "svg"))
    my_plotter.code.connect(c_output)
    my_svg_renderer = svg_renderer()
    c_output.connect(my_svg_renderer)
