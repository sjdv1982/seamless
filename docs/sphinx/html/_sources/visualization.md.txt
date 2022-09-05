# Visualization

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