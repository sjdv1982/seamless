# DOC = Display Object Class, from IPython.display

# TODO: add more mimetypes, see module-IPython.display documentation

import json

mimetype_to_DOC = {
    "text/html": "HTML",
    "image/png": ("Image", {"format": lambda cell: "png"}),
    "text/plain": "Pretty",
    'text/x-chdr': ("Code", {"language": lambda cell: "c"}),
    "application/json": "JSON",
}

celltype_to_DOC = {
    "structured": "JSON",
    "text": "Pretty",
    "code": ("Code", {"language": "language"}),
    "plain": "JSON", 
    # "mixed", 
    "binary": "JSON",
    "cson": "Pretty",
     "yaml": "Pretty",
    "str": "Pretty", 
    #"bytes"
    "int": "Pretty", 
    "float": "Pretty", 
    "bool": "Pretty", 
}

def json_widget(data, **kwargs):
    """ 
    # IPython.display.JSON does not work in notebooks 
    # (it does work in JupyterLab)
    # TODO: somehow check if we are inside a notebook,
    #  or else monkey-patch IPython.display.JSON?
    import IPython.display
    if isinstance(data, (str, int, bool, float)):
        data = [data]
    return IPython.display.JSON(data, **kwargs)
    """
    import IPython.display
    txt = json.dumps(data, sort_keys=True, indent=2)
    return IPython.display.Pretty(txt, **kwargs)

def select_DOC(celltype, mimetype):
    import IPython.display
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
    if classname == "JSON": # monkey patch
        DOC = json_widget
    return DOC, classname, params


def get_doc_kwargs(cell, params):
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
    return doc_kwargs

class OutputWidget:
    value = None
    def __init__(self, cell, layout=None):
        from ipywidgets import Output
        if layout is None:
            self.output_instance = Output()
        else:
            self.output_instance = Output(layout=layout)
        DOC, DOC_name, params = select_DOC(cell.celltype, cell.mimetype)
        doc_kwargs = get_doc_kwargs(cell, params)        
        self.DOC = DOC
        self.DOC_name = DOC_name
        self.doc_kwargs = doc_kwargs
        self.traitlet = cell.traitlet()
        self.traitlet.observe(self._update0)
        self.celltype = cell.celltype
        self.mimetype = cell.mimetype
        v = self.traitlet.value
        if v is not None:
            self._update(v)
    
    def _update(self, value):
        from ..silk import Silk
        from ..mixed.get_form import get_form
        from IPython.display import clear_output
        outdated = False
        tcelltype, tmimetype = self.traitlet.celltype, self.traitlet.mimetype
        if tcelltype is not None and tcelltype != self.celltype or tmimetype != self.mimetype:
            DOC, DOC_name, params = select_DOC(tcelltype, tmimetype)
            if DOC_name != self.DOC_name:
                outdated = True
            elif get_doc_kwargs(cell, params) != self.doc_kwargs:
                outdated = True
            else:
                self.celltype = tcelltype
                self.mimetype = tmimetype
        if outdated:
            value = "<Outdated>"
        if isinstance(value, Silk):
            value = value.unsilk
        try:
            form, _ = get_form(value)
            if form == "pure-plain":
                pass
            elif form == "pure-binary":
                value = value.tolist()
        except:
            value = "<Cannot be displayed>"
        if self.DOC_name == "Pretty":
            value = str(value)
        self.value = value
        self.refresh()

    def refresh(self):
        if self.value is None:
            return
        display_object = self.DOC(data=self.value,**self.doc_kwargs)        
        o = self.output_instance
        if len(o.outputs):
            o.clear_output(wait=True)
        o.outputs = () # Otherwise, doesn't clear; bug in ipywidgets?
        o.append_display_data(
            display_object
        )

    def _update0(self, change):
        return self._update(change.new)

    def set_cell(self, cell):
        pass

    def __repr__(self):
        return repr(self.output_instance)

    def __getattribute__(self, attr):
        if attr.startswith("_repr_") or attr.startswith("_ipython_"):
            return getattr(self.output_instance, attr)
        return super().__getattribute__(attr)
            
