Standard library
================

**As of seamless 0.1, the standard library is highlu unstable
and under development.**

*There is no formal documentation of the standard library yet. Check the
examples and tests to see how to use the standard library as it is now.*

*Below is a short description of each component of the current standard
library (as of seamless 0.1):*

link
^^^^^^^^^^^^^^^^^^^^^^^^^^^^
**link** (`cell`, `directory=None`, `filename=None`, \*,
  `latency=0.2`, `file_dominant=False` ).

Continuously synchronizes the value of `cell` and `directory/filename`.

`directory` and `filename` are optional if the cell has a .resource.filepath
defined (e.g. using ``cell.fromfile(...)``).

`latency`: how often the file is polled, in seconds (default 0.2).

`file_dominant (default False)`:
  - if False, when the context is loaded, a changed file is overwritten
    by the cell.
  - if True, when the context is loaded, a changed file overwrites the cell.

edit
^^^^^^^^^^^^^^^^^^
**edit** (`cell`)

Creates a reactor rc that contains PyQt5 GUI code to edit `cell`

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

As of seamless 0.1, the browser code cells is very minimalist.
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
  - `result`. The string that describes which template is to be evaluated
    to generate the result. The generated text is available on the `RESULT` outputpin.

Each template has access to the environment and to the evaluated value of
each other template. By analyzing the template text, templateer builds
a dependency tree of the templates.

See lib/plotly for example on how templateer can be used.


dynamic_html
^^^^^^^^^^^^^^^^^^^^

TODO


plotly
^^^^^^^^^^^^^^^^^^^^

TODO


ngl
^^^^^^^^^^^^^^^^^^^^

TODO

slash
^^^^^
lib.slash.slash0
****************
Slash is a bash replacement. Requires Linux/OSX.

Examples of slash can be seen in the docking examples (requires ATTRACT to be
installed: http://www.attract.ph.tum.de).

A very preliminary documentation of slash is in docs/WIP/

glprogram
^^^^^^^^^

lib.gl.glprogram
^^^^^^^^^^^^^^^^^
**glprogram** (`program`, `with_window=True`, `window_title="GLProgram"`):

Creates an OpenGL rendering program.

Below is **an incomplete summary of the essential features** .
Examples can be found in the fireworks example and the 3D example directory.
For the complete details, study the glprogram source code.

Each glprogram has `vertex_shader` and `fragment_shader` inputpins for the
shader code.

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
