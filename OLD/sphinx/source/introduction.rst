Introduction
============

Seamless: a cell-based reactive programming framework
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Seamless is a framework to set up computations (and visualizations) that respond
live to changes in cells. Cells contain the input data as well as the
source code of the computations, and all cells can be edited interactively.

The main application domains are scientific protocols, data visualization, and
interactive code development (algorithms, GUIs and shaders).

**Installation**: pip install seamless-framework

**Requirements**: Python 3.5+, IPython, PyQt5 (including QWebEngine),
 numpy, cson, PyOpenGL
*Recommended*: scipy, pandas, websockets, cython

**NOTE: For live programming, seamless must be run interactively within
IPython (from the command line: ipython -i script.py)**

For convenience, a command line tool ``seamless`` is provided, that starts up
 IPython and also imports the seamless API.

The nine seamless constructs (sorted from good to ugly):
  1. context
  2. cell
  3. transformer
  4. pin
  5. reactor
  6. macro
  7. export
  8. registrar
  9. observer
