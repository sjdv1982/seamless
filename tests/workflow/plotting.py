from seamless.workflow import Context

ctx = Context()


def plot(period, npoints):
    import matplotlib.pyplot as plt
    import numpy as np

    points = np.arange(npoints)
    phase = points / period * np.pi * 2
    fig, ax = plt.subplots()
    ax.plot(np.sin(phase))
    from io import BytesIO

    png = BytesIO()
    plt.savefig(png)
    return png.getvalue()


ctx.plot = plot
ctx.plot.period = 100
ctx.plot.npoints = 1000
ctx.png = ctx.plot
ctx.png.celltype = "bytes"
ctx.png.mimetype = "png"
ctx.png.share("plot.png")
ctx.compute()
print("open http://localhost:5813/ctx/plot.png in the browser")
