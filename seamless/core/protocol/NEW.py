"""Loose ends from other files, to be integrated"""
# from cell.py:

class Cell:
    def _checksum(self, value, *, buffer=False, may_fail=False):
        if value is None:
            return None
        v = str(value)
        if buffer and self._storage_type == "text":
            v = v.rstrip("\n")
        return get_hash(v,hex=True)

    # Don't forget the extra newline
    def serialize_buffer(self):
        v = self._val.rstrip("\n")
        return v + "\n"

class ArrayCell:
    #also provides copy+silk and ref+silk transport, but with an empty schema, and text form

    _supported_modes = []
    for transfer_mode in "buffer", "copy", "ref":
        _supported_modes.append((transfer_mode, "object", "binary"))
    del transfer_mode

    def _checksum(self, value, *, buffer=False, may_fail=False):
        if value is None:
            return None
        if buffer:
            return super()._checksum(value)
        assert isinstance(value, np.ndarray)
        b = self._value_to_bytes(value)
        return super()._checksum(b, buffer=True)

    def _value_to_bytes(self, value):
        b = BytesIO()
        np.save(b, value, allow_pickle=False)
        return b.getvalue()

    def _from_buffer(self, value):
        if value is None:
            return None
        b = BytesIO(value)
        return np.load(b)

class MixedCell:
    _supported_modes = []
    for transfer_mode in "buffer", "copy", "ref":
        _supported_modes.append((transfer_mode, "object", "mixed"))
    del transfer_mode
    _supported_modes = tuple(_supported_modes)


    def _assign(self, value):
        from seamless.mixed.get_form import get_form
        result = super()._assign(value)
        storage, form = None, None
        if self._val is not None:
            storage, form = get_form(self._val)
        self.storage_cell.set(storage, force=True)
        self.form_cell.set(form, force=True)
        return result

class TextCell:
    _supported_modes = []
    for transfer_mode in "buffer", "copy":
        _supported_modes.append((transfer_mode, "text", "text"))
        _supported_modes.append((transfer_mode, "object", "text"))
    _supported_modes = tuple(_supported_modes)
    del transfer_mode

class PythonCell:

    is_function = None
    func_name = None

    _supported_modes = []
    for transfer_mode in "buffer", "copy":
        for access_mode in "text", "pythoncode", "object":
            _supported_modes.append((transfer_mode, access_mode, "python"))
    _supported_modes = tuple(_supported_modes)
    del transfer_mode, access_mode

    def _text_checksum(self, value, *, buffer=False, may_fail=False):
        v = str(value)
        v = v.rstrip("\n") + "\n"
        return get_hash(v,hex=True)

    def _checksum(self, value, *, buffer=False, may_fail=False):
        if value is None:
            return None
        if buffer:
            return self._text_checksum(value, buffer=True, may_fail=may_fail)
        tree = ast.parse(value)
        dump = ast.dump(tree).encode("utf-8")
        return get_hash(dump,hex=True)

    def _validate(self, value):
        from .protocol import TransferredCell
        if isinstance(value, TransferredCell):
            value = value.data
        if inspect.isfunction(value):
            code = inspect.getsource(value)
            code = strip_source(code)
            value = code
        ast = cached_compile(value, self._codetype, "exec", PyCF_ONLY_AST)
        is_function = (len(ast.body) == 1 and
                       isinstance(ast.body[0], FunctionDef))
        is_expr = (len(ast.body) == 1 and
                       isinstance(ast.body[0], Expr))
        #no multiline expressions, may give indentation syntax errors
        if len(value.splitlines()) > 1:
            is_expr = False

        if is_function:
            self.func_name = ast.body[0].name
        elif is_expr:
            if isinstance(ast.body[0].value, Lambda):
                self.func_name = "<lambda>"
            else:
                self.func_name = "<expr>"
            is_function = True
        else:
            self.func_name = self._codetype

        self.is_function = is_function

class PyReactorCell: #Same for transformer/macro, but with _codetype = "transformer"
    """Python code object used for reactors
    a "PINS" object will be inserted into its namespace"""

    _codetype = "reactor"
    _supported_modes = []
    for transfer_mode in "buffer", "copy":
        _supported_modes.append((transfer_mode, "text", _codetype))
        _supported_modes.append((transfer_mode, "object", _codetype))
    _supported_modes.append(("ref", "pythoncode", _codetype))
    _supported_modes = tuple(_supported_modes)
    del transfer_mode

    def _validate(self, value): #only for reactor/macro
        super()._validate(value)
        assert self.func_name not in ("<expr>", "<lambda>") #cannot be an expression

class IPythonCell:
    _supported_modes = []
    for transfer_mode in "buffer", "copy":
        _supported_modes.append((transfer_mode, "text", "ipython"))
        _supported_modes.append((transfer_mode, "object", "ipython"))
    _supported_modes = tuple(_supported_modes)
    del transfer_mode

class PlainCell:
    _supported_modes = []
    for transfer_mode in "buffer", "copy", "ref":
        for access_mode in "json", "text", "object":
            if access_mode == "text" and transfer_mode == "ref":
                continue
            _supported_modes.append((transfer_mode, access_mode, "json"))
    _supported_modes = tuple(_supported_modes)
    del transfer_mode, access_mode

class CsonCell:
    _supported_modes = []
    for transfer_mode in "buffer", "copy":
        for access_mode in "json", "text", "object":
            _supported_modes.append((transfer_mode, access_mode, "cson"))
    _supported_modes = tuple(_supported_modes)
    del transfer_mode, access_mode


#macro.py

class Macro:
    pass

from .. import cell, transformer, pytransformercell, link,  path, \
 reactor, pyreactorcell, pymacrocell, jsoncell, csoncell, mixedcell, \
 arraycell, mixedcell, signal, pythoncell, ipythoncell, libcell, libmixedcell
from ..structured_cell import StructuredCell, BufferWrapper
from ..context import context
names = ("cell", "transformer", "context", "pytransformercell", "link", 
 "path", "reactor", "pyreactorcell", "pymacrocell", "plaincell", "csoncell",
 "mixedcell", "arraycell", "pythoncell", "ipythoncell", "libcell", "libmixedcell")
names += ("StructuredCell", "BufferWrapper")
names = names + ("macro",)
Macro.default_namespace = {n:globals()[n] for n in names}
