# DOC = Display Object Class, from IPython.display

# TODO: add more mimetypes, see module-IPython.display documentation

mimetype_to_DOC = {
    "text/html": "HTML",
    "image/png": ("Image", {"format": lambda cell: "png"}),
    "text/plain": "Pretty",
    'text/x-chdr': ("Code", {"language": lambda cell: "c"}),
    "application/json": "JSON",
}

celltype_to_DOC = {
    #"structured":
    "text": "Pretty",
    "code": ("Code", {"language": "language"}),
    "plain": "JSON", 
    # "mixed", 
    # "binary",
    "cson": "Pretty",
     "yaml": "Pretty",
    "str": "Pretty", 
    #"bytes"
    "int": "Pretty", 
    "float": "Pretty", 
    "bool": "Pretty", 
}

def json_widget(data, **kwargs):
    import IPython.display
    if isinstance(data, (str, int, bool, float)):
        data = [data]
    return IPython.display.JSON(data, **kwargs)

def select_DOC(cell):
    import IPython.display
    celltype = cell.celltype
    mimetype = cell.mimetype
    classname, params = None, None
    if mimetype in mimetype_to_DOC:
        result = mimetype_to_DOC[mimetype]
    elif celltype in celltype_to_DOC:
        result = celltype_to_DOC[celltype]
    else:
        result = None
    if result is not None:
        if isinstance(result, str):
            classname = result
        else:
            classname = result[0]
            params = result[1].copy()
    if classname is None:
        msg = "Celltype '%s'" % celltype
        if mimetype is not None:
            msg += ", mimetype '%s'" % mimetype
        msg += "cannot be displayed in IPython"
        raise Exception(msg)
    DOC = getattr(IPython.display, classname)
    '''
    if classname == "TextDisplayObject":
        DOC = lambda data, **kwargs: str(data) # does not work well otherwise
    '''
    if classname == "JSON": # monkey patch
        DOC = json_widget
    return DOC, params


class OutputWidget:

    def __init__(self, cell, layout=None):
        from ipywidgets import Output
        if layout is None:
            self.output_instance = Output()
        else:
            self.output_instance = Output(layout=layout)
        DOC, params = select_DOC(cell)
        doc_kwargs = {}
        if params is not None:
            for name, value in params.items():
                if isinstance(value, str):
                    v = getattr(cell, value)
                elif callable(value):
                    v = value(cell)
                else:
                    raise TypeError((name, value))
                doc_kwargs[name] = v
        self.DOC = DOC
        self.doc_kwargs = doc_kwargs
        traitlet = cell.traitlet()
        traitlet.observe(self._update)
    
    def _update(self, change):
        value = change.new
        display_object = self.DOC(data=value,**self.doc_kwargs)        
        self.output_instance.clear_output()
        self.output_instance.outputs = () # Otherwise, doesn't clear; bug in ipywidgets?
        self.output_instance.append_display_data(
            display_object
        )

    def __repr__(self):
        return repr(self.output_instance)

    def __getattr__(self, attr):
        if attr.startswith("_repr_") or attr.startswith("_ipython_"):
            return getattr(self.output_instance, attr)
        raise AttributeError(attr)
            
