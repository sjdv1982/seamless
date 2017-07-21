Standard library
================

**As of seamless 0.1, the standard library is in a very early stage.
Documentation is incomplete.**

`Beyond the documentation below, check the examples and tests to see how to use
the standard library (as it is now).`

link
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
**link** (`cell`, `directory=None`, `filename=None`, \*,
  `latency=0.2`, `file_dominant=False` ).

Continuously synchronizes the value of `cell` and `./directory/filename`.

`directory` and `filename` are optional if the cell has a `.resource.filepath`
defined (e.g. using ``cell.fromfile(...)``).

`latency`: how often the file is polled, in seconds (default 0.2).

`file_dominant (default False)`:
  - if False, when the context is loaded, a changed file is overwritten
    by the cell.
  - if True, when the context is loaded, a changed file overwrites the cell.

edit
^^^^^^^^^^^^^^^^^^
**edit** (`cell`)

Creates a reactor `.rc` that contains PyQt5 GUI code to edit `cell`

As of seamless 0.1, `cell` may have the following data types:
int, float, str, json

The reactor is wrapped in a context::

  e = edit(cell)
  e.rc   # => reactor
  e.rc.code_start.cell()  # => reactor source code

As of seamless 0.1, the PyQt5 code cells are very minimalist.
Contributions are most welcomed.

combobox
^^^^^^^^^^^^^^^^^^

Edits an cell, similar to ``edit(...)``, but as a combobox rather
than as a spinbox or textedit.
Requires a list of options to be provided via the inputpin `options`.

playcontrol
^^^^^^^^^^^^^^^^^^

Edits an "int" cell, similar to ``edit(...)``, but provides controls
similar to a movie player. Used in one of the docking examples.

display
^^^^^^^^^^^^^
**display** (`cell`)

Same as **edit**, but only displays the cell value, does not edit it.

As of seamless 0.1, the PyQt5 code cells are very minimalist.
Contributions are most welcomed.

browse
^^^^^^^^^^^^^
**browse** (`cell`)

Same as **display**, but displays the cell's content in a window containing a
minimal PyQt5 browser widget.

As of seamless 0.1, the cell must be of dtype ("text", "html").

As of seamless 0.1, the browser code cells are very minimalist.
Contributions are most welcomed.

init
^^^^^^^^^^^^^^^^^^^^
A simple reactor that sends a signal on `.trigger` when it starts up.


timer
^^^^^^^^^^^^^^^^^^^^
A reactor that periodically sends a signal on `.trigger`.

`period` can be provided as parameter or it can be connected as an inputpin.


filehash
^^^^^^^^^^^^^^^^^^^^
Similar to **link**, but it works unidirectionally (files are monitored, but
not written to), and instead of its value, the file's md5 hash is returned.


itransformer
^^^^^^^^^^^^^^^^^^^^
Works like a standard transformer, except that the `code` inputpin is for
an IPython cell ( `dtype=("text", "code", "ipython")` ).

See tests/test-itransformer.py for an example where an itransformer is used to
compile and execute Cython code.


templateer
^^^^^^^^^^^^^^^^^^^^

**templateer** ( `params`) Generates text (usually HTML) based on
Jinja templates.

`params` is a dictionary of three items:
  - `environment`. A dict of (`name`, `dtype`) items.
    Each item becomes an inputpin.
  - `templates`. A list of `template_name` strings.
    Each template name becomes a text inputpin, containing a Jinja template.
  - `result`. The string that describes which of the templates is to be
    evaluated to generate the result.
    The generated text is available on the `RESULT` outputpin.

Each template has access to the environment and to the evaluated value of
each other template. By analyzing the template text, templateer builds
a dependency tree of the templates.

See lib/plotly for an example on how templateer can be used.


dynamic_html
^^^^^^^^^^^^^^^^^^^^

**dynamic_html** ( `params`) sets up a Seamless-to-browser bridge.

dynamic_html generates JavaScript that listens to the seamless websocketserver.
This JavaScript should be placed inside the body of an HTML file

As of seamless 0.1, dynamic_html only supports unidirectional communication
`seamless => browser`, not yet `browser => seamless`.

`params` is a dict of (name, value) items, each of which becomes
an inputpin of that name. 'value' is a dict with the following items:

- `type`: can be "HTML", "eval" or "var" (variable).

  Inputpin cells of type
  "HTML" must contain HTML, those of type "var" must contain JSON, and
  those of type "eval" must contain JavaScript.

- `id` (only if `type` is "HTML"): the div element name of the item. Whenever
  the inputpin changes, the HTML value of the div element is updated.

- `var` (only if `type` is "var"): the JavaScript name of the variable

- `dtype` (only if `type` is "var"): the dtype of the variable

- `evals` (only if `type` is "var"): a list of inputpin names of type "eval".
  Whenever the variable is updated, the JavaScript code of each inputpin
  in `evals` is executed in order.

The generated JavaScript is available under the `RESULT` outputpin.
It contains the value of IDENTIFIER, which is unique for every dynamic_html
instance (and indeed, for every reactor instance). The Seamless websocketserver
waits for clients to identify themselves with an IDENTIFIER, and will forward
every message that was sent to it by a dynamic_html reactor under that
IDENTIFIER. This way, multiple clients can listen to the same dynamic_html,
and all dynamic_html reactors use the same websocketserver. The seamless
websocket is by default 5678, but if it is already in use, the next socket is
used. This, too, is reflected in the generated JavaScript.

see test/dynamic-html-lib.py for a simple example.
dynamic_html is used by lib.plotly and lib.ngl


plotly
^^^^^^^^^^^^^^^^^^^^

**plotly** ( `*`, `dynamic_html`, `mode`)

An interface to the plotly.js plotting library. The plotly macro generates
static Plotly HTML that is to be displayed in a browser.

Only the macro that provides the Plotly interface is documented here. For
documentation on Plotly itself, see the plotly.js website.

**NOTE**: in Plotly, the `data` dict contains a list of data series, and each
series contains both the data itself (x/y/z) and its presentation details
(plotting modes, marker colors, symbols, legends, etc).
In contrast, as of seamless 0.1, the plotly macro expects only the data
itself in `data`,
and all presentation details in `attrib`. Moreover, the format of the data
depends on the `mode` parameter. All of this may undergo small or large changes
in future versions of seamless.

Parameters
**********

- `dynamic_html` (keyword-only, default=False): If True, generates dynamic HTML
  that reflects updates in the cells without the need of a browser reload.
  See lib.dynamic_html for more details.

  NOTE: as of seamless 0.1, this does not work very well for Plotly.

- `mode` (keyword-only, default="manual"): Determines the data format of the
  `data` inputpin. As of seamless 0.1, it can be "manual", "nx" or "nxy".

  See below for more details.

Input pins
************

- `title` (str): Title of the plot

- `data`: Contains the data of the plot, essentially the x/y/z data. The format
  depends on the `mode` parameter.

  If `mode` is "manual", `data` is in JSON format, with the same schema
  as Plotly uses:

    - `data` is a list of data series dicts
    - Each of those dicts contains `x`, `y` and/or `z` attributes
    - Each of those attributes is a list of values.

  If `mode` is "nx", `data` is in text (CSV) format. Every column must be
  a separate data series that only has an `x` value. There are no headers.

  If `mode` is "nxy", `data` is in text (CSV) format. Every column must describe
  a separate variable, and every row must describe a separate observation (data
  series). The first line must be a header that contains the variable names for
  each column. Data series names are defined elsewhere in `attrib`.

- `attrib` (JSON): The presentation details of the data, i.e. everything
  that is in the Plotly `data` dict except x/y/z.

- `layout` (JSON): The Plotly `layout` dict.

- `config` (JSON): The Plotly `config` dict.

Output pins
************

- `html` : the outputpin that contains the generated static HTML, to be
  displayed in a browser.

- `dynamic_html` : the outputpin that contains the generated dynamic HTML, to be
  displayed in a browser. Is only generated if ``dynamic_html=True``


ngl
^^^^^^^^^^^^^^^^^^^^

Sets up dynamic HTML code to view molecules using the NGL molecular viewer

See examples/docking/docking.py for an example.


Parameters
******************
   - `molnames`: either a list of molecule names (molnames) or a
     dict of `(molname, dataformat)` items, where `dataformat` is any
     format understood by ``NGL.Stage.loadFile()``.

     See:

     - http://arose.github.io/ngl/api/manual/usage/file-formats.html

     - http://arose.github.io/ngl/api/Stage.html

     If `molname` is a list, the dataformat for all molecules is PDB.

Input pins
**********

  - `data_X` (where X is each molname): A text pin for the molecule data.
    As of seamless 0.1, only text is supported

  - `transformation_X`: A JSON cell for the molecule rotation+translation matrix.
     Must be a 4x4 matrix in JSON format (list of lists)

     Default: identity matrix

  - `representations`: A JSON pin containing the molecular representations.
    The representations are a list of dicts, with each dict containing the
    following keys:

      - `repr`: the representation, as understood by NGL.
        Examples: "cartoon", "spacefill", "ball+stick", "licorice"
        See http://arose.github.io/ngl/api/manual/usage/molecular-representations.html

      - `obj`: Optional. A molname of list of molnames to which the
        representation applies. Default: all molnames

      All other keys are passed directly to ``NGL.Stage.addRepresentation()``
        Examples of keys:

        - color, colorScheme:
            Examples:

            ``"color": "red"``

            ``"colorScheme": "bfactor"``


            ``"colorScheme": "element"``

            See: http://arose.github.io/ngl/api/manual/usage/coloring.html

        - sele:
            Examples: "73-77", ":A", "LYS"

            See: http://arose.github.io/ngl/api/manual/usage/selection-language.html

Output pins
************
  - `html`: output pin containing the generated dynamic HTML, to be visualized

    As of seamless 0.1, requires that a copy or link to ngl.js is present in
    the current directory

slash
^^^^^
lib.slash.slash0
****************
Slash is a bash (shell script) replacement. Requires Linux.
OSX should work too, but has not currently been tested.

Examples of slash can be seen in the docking examples (requires ATTRACT to be
installed: http://www.attract.ph.tum.de).

A very preliminary documentation of slash is in docs/WIP/

glprogram
^^^^^^^^^

lib.gl.glprogram
****************

**glprogram** (`program`, `with_window=True`, `window_title="GLProgram"`):

Creates an OpenGL rendering program.

Below is **an incomplete summary of the essential features** .
Examples can be found in the fireworks example and the 3D example directory.
For the complete details, study the glprogram source code.

The `program` parameter is a dictionary. The following examples of program
parameter dicts are available in the examples/3D folder:

  - lines.cson
  - triangles-flat.cson
  - triangles-smooth.cson
  - atom.cson

The program parameter dictionary specifies:
  - `arrays`: the names X, Y, ... of the array_X, array_Y, ... array pins that
    are linked to the program.

  - `uniforms`: these are linked directly to the shader.

  - `render`: must contain the rendering command and a specification of the
    vertex attributes. The resource access expression (rae) defines how to get
    the attribute out of the array: ``{"array": "spam", "rae": "ham[:10]"}`` =>
    ``attribute = spam["ham"][:10]``. To make this work, `spam` must be a
    structured numpy array with a member "ham".

Each glprogram has `vertex_shader` and `fragment_shader` inputpins for the
shader code.

Buffers linked to the array pins must be array cells with ``.set_store("GL")``
(for vertex buffers) or ``.set_store("GLTex", N)`` (for N-dimensional textures).

If ``with_window=True`` (the default), the glprogram sets up its own Qt OpenGL
window in which the program does its rendering.

If ``with_window=False``, the glprogram relies on signals from an external
Qt OpenGL window. External windows can be wrapped in a **glwindow**
(lib.gl.glwindow) instance. A glwindow
also has a ``.camera`` outputpin that provides modelview/projection matrices
that adapt to mouse-click movements.
For more information, see examples/3D/test-atom.py, or study the glwindow source.
