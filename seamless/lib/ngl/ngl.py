from seamless import macro

@macro("json")
def ngl(ctx, molnames):
    """
    Sets up dynamic HTML code to view molecules using the NGL viewer

    Generates a context with the following pins:
    Inputs:
      data_X (where X is each molname): A text pin for the molecule data.
        As of seamless 0.1, only text is supported
      transformation_X: A JSON cell for the molecule rotation+translation matrix.
         Must be a 4x4 matrix in JSON format (list of lists)
         Default: identity matrix
      representations: A JSON pin containing the molecular representations
        The representations are a list of dicts, with each dict containing the
         following keys:
          repr: the representation, as understood by NGL.
            Examples: "cartoon", "spacefill", "ball+stick", "licorice"
            See http://arose.github.io/ngl/api/manual/usage/molecular-representations.html
          obj: Optional. A molname of list of molnames to which the
            representation applies. Default: all molnames
          All other keys are passed directly to NGL.Stage.addRepresentation()
            Examples of keys:
            color, colorScheme:
                Examples: color: "red", colorScheme: "bfactor" / "element"
                See: http://arose.github.io/ngl/api/manual/usage/coloring.html
            sele:
                Examples: "73-77", ":A", "LYS"
                See: http://arose.github.io/ngl/api/manual/usage/selection-language.html
    Output:
      html: output pin containing the generated dynamic HTML, to be visualized
        As of seamless 0.1, requires that a copy or link to ngl.js is present in
         the current directory

    Macro arguments:
       molnames: is either a list of molecule names in PDB format, or a
         dict of (moleculename, dataformat) items, where dataformat is any
         format understood by NGL.Stage.loadFile()
         See: http://arose.github.io/ngl/api/manual/usage/file-formats.html
              http://arose.github.io/ngl/api/Stage.html
    """
    from seamless import cell, transformer, reactor
    from seamless.lib.dynamic_html import dynamic_html
    from seamless.lib.templateer import templateer
    from seamless.core.worker import ExportedInputPin, ExportedOutputPin


    ctx.tmpl = cell("text").fromfile("ngl-html.jinja")

    if isinstance(molnames, list):
        molnames = {name:"pdb" for name in molnames}

    params = {
      "update_": {
        "type": "eval"
      }
    }
    for molname, dataformat in molnames.items():
        newparams = {
          "data_" + molname:  {
            "type": "var",
            "var": "update.data_" + molname,
            "dtype": "text",
            "evals": ["update_"]
          },
          "dataformat_" + molname:  {
            "type": "var",
            "var": "update.dataformat_" + molname,
            "dtype": "text",
            "evals": ["update_"]
          },
          "representations_" + molname:  {
            "type": "var",
            "var": "update.representations_" + molname,
            "dtype": "json",
            "evals": ["update_"]
          },
          "transformation_" + molname:  {
            "type": "var",
            "var": "update.transformation_" + molname,
            "dtype": "json",
            "evals": ["update_"]
          },
        }
        params.update(newparams)

    ctx.dynamic = dynamic_html(params)
    ctx.templateer = templateer({"templates": ["tmpl"], "environment": {"dynamic": ("text", "html")}})
    ctx.tmpl.connect(ctx.templateer.tmpl)
    ctx.dynamic.dynamic_html.cell().connect(ctx.templateer.dynamic)

    ctx.update_ = cell("text")
    ctx.update_.set("do_update()");
    ctx.update_.connect(ctx.dynamic.update_)


    transformer_params = {
        "molnames": {"pin": "input", "dtype": "json"},
        "representations": {"pin": "input", "dtype": "json"}
    }
    for molname, dataformat in molnames.items():
        pinname = "dataformat_" + molname
        pin = getattr(ctx.dynamic, pinname)
        pin.cell().set(dataformat)

        pinname = "transformation_" + molname
        c = cell("json").set([[1,0,0,0],[0,1,0,0], [0,0,1,0], [0,0,0,1]])
        setattr(ctx, "cell_transformation_" + molname, c)
        c.connect(getattr(ctx.dynamic, pinname))
        setattr(ctx, "transformation_" + molname, ExportedInputPin(c))

        pinname = "representations_" + molname
        transformer_params[pinname] = {"pin": "output", "dtype": "json"}

    # As of seamless 0.1, this has to be a reactor due to multiple outputs
    t = ctx.transform_representations = reactor(transformer_params)
    t.molnames.set(list(molnames.keys()))
    t.code_start.cell().set("")
    t.code_update.cell().fromfile("cell-transform-representations.py")
    t.code_stop.cell().set("")
    for molname, dataformat in molnames.items():
        pinname = "representations_" + molname
        source = getattr(t, pinname).cell()
        target = getattr(ctx.dynamic, pinname)
        source.connect(target)

    ctx.representations = ExportedInputPin(t.representations)


    ctx.export(ctx.dynamic)
    ctx.html = ExportedOutputPin(ctx.templateer.RESULT)
