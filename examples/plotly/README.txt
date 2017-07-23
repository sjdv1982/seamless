./test-plotly.py

Plotting example, using Plotly (www.plotly.js).

Run the program, and live-edit the following files:
- data.csv: The raw data.
- attrib.cson: The data representation (legends, markers, etc.).
See the Plotly  documentation on data representation for more details.
If Plotly was accessed directly from JavaScript, this would go into the data
dict, but in seamless, the Plotly data dict is split into data and attrib.
- layout.cson: The layout of the plot. See the Plotly documentation on layout
for more details.

The example uses the seamless plotly macro (see documentation) to generate
Plotly HTML.
This example displays both static and dynamic HTML. The static HTML is
regenerated every time the data/attrib/layout cells change. The dynamic HTML
doesn't change, but receives cell updated via the seamless websocketserver.
As of seamless 0.1, the dynamic HTML does not work very well for Plotly.
