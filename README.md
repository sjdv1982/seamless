Seamless: a cell-based reactive programming framework
=====================================================

Seamless is a framework to set up computations (and visualizations) that respond
to changes in cells. Cells contain the input data as well as the source code of
the computations, and all cells can be edited live.

The main application domains are scientific protocols, data visualization, and
live code development (scientific algorithms).

**Installation**: pip install seamless-framework

**Requirements**: Python 3.5+, IPython, numpy, cson, websockets, requests, wurlitzer, aiohttp, aiohttp_cors

NOTE: Seamless runs very well with Jupyter, but requires tornado-4.5.3, not tornado 5.1!
NOTE: Seamless requires IPython 6, not IPython 7!

*Recommended*: scipy, pandas, cython, PyQt5 (including QWebEngine)
