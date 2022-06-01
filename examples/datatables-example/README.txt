This example computes a JSON structure representing a datatable.
This structure is visualized in HTML with the "itables" library,
 using jquery's datatables.
The datatable computation can be customized interactively,
  either inside a Jupyter notebook (ipywidgets).
  or within a HTML web interface (simple sliders) that also displays the datatable.

***NOTE: Seamless has an automatic web interface generator, 
but this is NOT used in this example.
Instead, the HTML web interface (datatables-dynamic.html, datatables-dynamic.js)
has been manually written.

Other Seamless examples "webserver-example" and "webserver-demo" DO use the 
automatic web interface generator, and are simpler to follow.

However, the current example is much easier to understand 
in terms of what happens exactly.

The Seamless web interface generator also has a datatable web component
(TODO: example for this)
***


Building the workflow
=====================

First the build-workflow-graph.py script must be run with `seamless-run python`.
(This has already been done.)
The script is documented, describing step-by-step how the workflow is built.

The script will compute an initial datatable, and generate the following files:

- datatables.seamless + datatables.zip. 
This is the Seamless workflow graph that is loaded in the notebook.

- datatables-static.html. The visualization of the initial datatable as static HTML.
You can open it in your browser, but it will never update.

The workflow contains HTML and Javascript cells that describe a simple, 
hand-coded web interface, with sliders to control the parameters, and
embedding the generated datatable dynamically.
Since these cells are shared over HTTP, you can open the web interface in your browser 
after loading the workflow graph.


Visualization using Jupyter 
===========================

Then, run the datatables.ipynb notebook. The notebook will build a little dashboard 
using Jupyter widgets. 
With this dashboard, you can see the generated datatable and control its parameters.
Note that the Jupyter notebook doesn't define the workflow itself, but simply loads it 
from file. 
Since the web interface is contained inside the workflow,
it becomes accessible when the workflow is loaded in Jupyter.
You can interactively control and visualize the datatable using the dashboard, 
the web interface, or both, as Seamless keeps them in sync.
Multiple instances of the web interface are also kept in sync, making the web interface
collaborative.

Visualization of the web interface alone
========================================

- Run "seamless-serve-graph datatables.seamless datatables.zip". 
  Ctrl+C will end the visualization.
- Open http://localhost:5813 in the browser.
