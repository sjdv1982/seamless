# Visualization

The goal of visualization is the interactive visualization and editing of Seamless cells in the browser. This can be done either via Jupyter, or directly using the [Seamless shareserver](http://sjdv1982.github.io/seamless/sphinx/html/shareserver.html)

***IMPORTANT: This documentation section is a draft. The preliminary text is shown below***

## Using Jupyter notebooks

*User experience* (UX) can be done initially using Jupyter notebooks (very quick to set up). See [this simple test](https://github.com/sjdv1982/seamless/blob/stable/tests/highlevel/traitlets.ipynb), to be opened with `seamless-jupyter`.

## Using web visualization

**Relevant examples:**

- [datatables](https://github.com/sjdv1982/seamless/tree/stable/examples/datatables-example)

- [grid editor](https://github.com/sjdv1982/seamless/tree/stable/examples/grid-editor-example)

See [Running examples](https://sjdv1982.github.io/seamless/sphinx/html/getting-started.html#running-examples-locally) on how to run examples.

More powerful is to use UX cells (HTML, JS, CSS). These cells are shared over HTTP (read-only), so that they can be accessed via the browser. Input cells (read-write) and output cells (read-only) are also shared over HTTP, so that the UX cells (loaded in the browser) can access and manipulate them. See [this test](https://github.com/sjdv1982/seamless/blob/stable/tests/highlevel/share-pdb.py), to be opened with `seamless-ipython -i`.

## Web interface generator

**Relevant examples:**

- [webserver demo](https://github.com/sjdv1982/seamless/tree/stable/examples/webserver-demo)

- [webserver example](https://github.com/sjdv1982/seamless/tree/stable/examples/webserver-example)

See [Running examples](https://sjdv1982.github.io/seamless/sphinx/html/getting-started.html#running-examples-locally) on how to run examples.

A Seamless project automatically includes a web interface generator.
When you share a cell (and retranslate the graph), an entry is automatically added in
`/web/webform.json` . These entries are used to generate the web interface in `web/index.html` and `web/index.js`. The web interface is available under `http://localhost:<REST server port>`, normally `http://localhost:5813`.

- Each entry in `/web/webform.json` describes the web component for the cell, and its parameters. All web components are in `/web/components/`. The "component" attribute of an entry can be the name of any component in that folder. See the README for each component for the required parameters (the "params" attribute of the entry).

- You can also modify or create new components in `/web/components/`, and the web interface will be updated.

- You can manually edit `web/index.html` and `web/index.js`. Your modifications are automatically merged with the auto-generated HTML and JS. Sometimes, this can give rise to a merge conflict. Therefore, monitor and resolve `web/index-CONFLICT.html` and `web/index-CONFLICT.js`.

- Likewise, when a modified context leads to added or removed entries in `/web/webform.json`, and these are automatically merged with your modifications. Resolve `web/webform-CONFLICT.txt` in case of a conflict.

## Modifying the web status generator

TODO. Integrate/merge with "visualization and monitoring" in "Seamless explained".
<!--
TODO: from old "explained.md":

Typically, a web service consists of two graphs (.seamless files).
-The first graph contains the main workflow. The second graph contains a status gra
ph. The status graph can be bound by Seamless to the main graph (`seamless.metaleve
l.bind_status_graph`; this function is automatically invoked by `seamless-serve-gra
ph` if you provide two graph files). In that case, the status graph receives the cu
rrent value and status of the  main workflow graph as its input, and normally visua
lizes it as a web page. Manually-coded web interfaces are normally added to the mai
n workflow graph. In contrast, the automatic web interface generator is part of the
 status graph, as it generates the web interface HTML by taking the main workflow g
raph as an input. During development, both graphs are developed, which is made poss
ible by `seamless-new-project` and `seamless-load-project`.


TODO:

- Webunits

- ctx.path.x (Seamless Python) vs /ctx/path/x (HTTP) vs ctx.path__x (Javascript client). This is all for cells shared with .share() (no arguments), which become "cells" in the webform.

- "extra cells" are the ones with .share(path), where the sharepath ( HTTP+Javascript) is different from the Python path. They can be referred to in the ["cell" attribute / "cells" list attribute] of extra components.
In case of "cells", ctx.attr is guaranteed to work in Javascript. For extra cells, it may not..

### C4. Web status and web interface generation

Intro:

- Web status
- Web interface

Intermediate:

- Customizing the web status generator
- The Seamless client library (and customize it)
- Adding your own web components
- Customizing the web interface generator

In-depth:

- The metalevel, observers, and understanding the status generator
(secondary context)

Contributing your modifications
Github... Running test...

-->