This example computes a JSON structure representing a datatable.
This structure is visualized in HTML using the "itables" library.
The computation can be customized interactively inside a Jupyter notebook.

Building the workflow context
=============================

First run the gen-context.py script with Python.
This will compute an initial datatable, and generate the following files:

- datatables.seamless + datatables.zip. 
This is the Seamless context graph that is loaded in the notebook.

- datatables-static.html . The visualization of the initial datatable as static HTML.

The calculation of the datatable is very simple. Two integer sequences A
and B, with "first", "step", and "length" are defined.
...

Visualization using Jupyter 
===========================

Then, run the datatables.ipynb Notebook. The notebook will build a little 


Notes
=====

Seamless has a web interface generator, but this is not used in this example.
Instead, the web visualization (datatables-dynamic.html, datatables-dynamic.js) 
is manually written, and .

See the seamless ...

There is also a datatable component for the Seamless web interface generator.
(TODO: example for this)
