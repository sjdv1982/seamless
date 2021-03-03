from seamless.highlevel import Context

ctx = Context()
def plot(period, npoints):
    import matplotlib.pyplot as plt
    import mpld3
    import numpy as np
    points = np.arange(npoints)
    phase = points/period*np.pi*2
    fig, ax = plt.subplots()
    ax.plot(np.sin(phase))
    return mpld3.fig_to_html(fig)
ctx.plot = plot
ctx.plot.period = 100
ctx.plot.npoints = 1000
ctx.html = ctx.plot
ctx.html.mimetype = "html"
ctx.html.share("plot.html")
ctx.compute()
print("open http://localhost:5813/ctx/plot.html in the browser")