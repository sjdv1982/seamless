"""Loose ends from other files, to be integrated"""
# ALSO SEE THE COMMENTED-OUT SECTION OF ./protocol.py

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
 arraycell, mixedcell, signal, pythoncell, ipythoncell, libcell
from ..structured_cell import StructuredCell, BufferWrapper
from ..context import context
names = ("cell", "transformer", "context", "pytransformercell", "link", 
 "path", "reactor", "pyreactorcell", "pymacrocell", "plaincell", "csoncell",
 "mixedcell", "arraycell", "pythoncell", "ipythoncell", "libcell")
names += ("StructuredCell", "BufferWrapper")
names = names + ("macro",)
Macro.default_namespace = {n:globals()[n] for n in names}


#protocol.py


adapters = OrderedDict()
adapters[("copy", "object", "mixed"), ("copy", "text", "text")] = assert_mixed_text
adapters[("copy", "object", "mixed"), ("copy", "plain", "plain")] = assert_plain
adapters[("copy", "text", "cson"), ("copy", "plain", "cson")] = adapt_cson_json
adapters[("copy", "text", "cson"), ("copy", "plain", "plain")] = adapt_cson_json
for content_type1 in text_types:
    adapters[("copy", "text", content_type1), ("copy", "text", "plain")] = True
    adapters[("copy", "text", content_type1), ("copy", "text", "mixed")] = True
    adapters[("copy", "text", content_type1), ("copy", "object", "plain")] = True
    adapters[("copy", "text", content_type1), ("copy", "object", "mixed")] = True
    for content_type2 in text_types:
        if content_type1 == content_type2:
            continue
        adapters[("copy", "text", content_type1), ("copy", "text", content_type2)] = True

for content_type in ("text", "python", "ipython", "transformer", "reactor", "macro"):
    adapters[("copy", "text", "plain"), ("copy", "text", content_type)] = assert_text
    adapters[("copy", "text", content_type), ("copy", "text", "plain")] = json_encode
    adapters[("copy", "text", content_type), ("copy", "plain", content_type)] = True
adapters[("copy", "object", "mixed"), ("copy", "text", "mixed")] = assert_mixed_text
adapters[("copy", "object", "mixed"), ("copy", "plain", "mixed")] = assert_plain

for content_type in content_types:
    adapters[("copy", "object", content_type), ("copy", "object", "object")] = True
    adapters[("copy", "object", "object"), ("copy", "object", content_type)] = True
for content_type in ("plain", "mixed"):
    adapters[("ref", "object", content_type), ("ref", "object", "mixed")] = True
    adapters[("copy", "plain", content_type), ("copy", "object", "mixed")] = True
adapters[("copy", "object", "text"), ("copy", "object", "mixed")] = True
adapters[("ref", "plain", "plain"), ("ref", "silk", "plain")] = adapt_to_silk
adapters[("copy", "plain", "plain"), ("copy", "silk", "plain")] = adapt_to_silk
adapters[("copy", "plain", "cson"), ("copy", "silk", "cson")] = adapt_to_silk
adapters[("ref", "object", "mixed"), ("ref", "silk", "mixed")] = adapt_to_silk
adapters[("copy", "object", "mixed"), ("copy", "silk", "mixed")] = adapt_to_silk
adapters[("copy", "silk", "mixed"), ("copy", "object", "mixed")] = adapt_from_silk
adapters[("copy", "silk", "plain"), ("copy", "object", "plain")] = adapt_from_silk
for access_mode in "object", "text":
    adapters[("copy", access_mode, "python"), ("copy", access_mode, "ipython")] = True
adapters[("copy", "text", "python"), ("copy", "module", "python")] = True
adapters[("copy", "text", "python"), ("copy", "module", "ipython")] = True
adapters[("copy", "text", "ipython"), ("copy", "module", "ipython")] = True
for pymode in ("transformer", "reactor", "macro"):
    for lang in ("python", "ipython"):
        adapters[("ref", "pythoncode", lang), ("ref", "pythoncode", pymode)] = True
        adapters[("copy", "pythoncode", lang), ("copy", "pythoncode", pymode)] = True
    adapters[("copy", "text", "ipython"), ("copy", "pythoncode", pymode)] = adapt_ipython
adapters[("copy", "object", "mixed"), ("copy", "binary_module", "mixed")] = compile_binary_module
adapters[("ref", "object", "mixed"), ("ref", "binary_module", "mixed")] = compile_binary_module

def select_adapter(transfer_mode, source, target, source_modes, target_modes):
    #print("select_adapter", transfer_mode, source, target, source_modes, target_modes)
    if transfer_mode == "ref":
        transfer_modes = ["ref", "copy"]
    else:
        transfer_modes = [transfer_mode]
    for trans_mode in transfer_modes:
        for source_mode0 in source_modes:
            if source_mode0[0] != trans_mode:
                continue
            for target_mode in target_modes:
                source_mode = source_mode0
                target_mode = substitute_default(source_mode, target_mode)
                if target_mode[0] != trans_mode:
                    continue
                if source_mode[1] is None:
                    source_mode = (trans_mode, target_mode[1], source_mode[2])
                if source_mode[2] is None:
                    source_mode = (trans_mode, source_mode[1], target_mode[2])
                if target_mode[1] is None:
                    target_mode = (trans_mode, source_mode[1], target_mode[2])
                if target_mode[2] is None:
                    target_mode = (trans_mode, target_mode[1], source_mode[2])
                if source_mode == target_mode:
                    return None, (source_mode, target_mode)
                adapter = adapters.get((source_mode, target_mode))
                if adapter is not None:
                    if adapter is True:
                        return None, (source_mode, target_mode)
                    else:
                        return adapter, (source_mode, target_mode)
    raise Exception("""Could not find adapter between %s and %s

Supported source modes: %s

Supported target modes: %s

""" % (source, target, source_modes, target_modes))

def serialize(cell, transfer_mode, access_mode, content_type):    
    source_modes = list(cell._supported_modes)
    if transfer_mode == "ref":
        transfer_modes = ["ref", "copy"]
    else:
        transfer_modes = [transfer_mode]
    for trans_mode in transfer_modes:
        target_mode0 = trans_mode, access_mode, content_type
        for source_mode0 in source_modes:
            if source_mode0[0] != trans_mode:
                continue
            source_mode = source_mode0
            target_mode = substitute_default(source_mode, target_mode0)
            if target_mode[0] != trans_mode:
                continue
            if source_mode[1] is None:
                source_mode = (trans_mode, target_mode[1], source_mode[2])
            if source_mode[2] is None:
                source_mode = (trans_mode, source_mode[1], target_mode[2])
            if target_mode[1] is None:
                target_mode = (trans_mode, source_mode[1], target_mode[2])
            if target_mode[2] is None:
                target_mode = (trans_mode, target_mode[1], source_mode[2])
            if source_mode == target_mode:
                adapter = True
            else:
                adapter = adapters.get((source_mode, target_mode))
            if adapter is not None:
                value = cell.serialize(*source_mode)
                if value is None:
                    return None
                if adapter is True:
                    return value
                else:
                    return adapter(value)
    target_mode = transfer_mode, access_mode, content_type                    
    raise Exception("""Could not find adapter for cell %s

Requested mode: %s

Supported modes: %s

""" % (cell, target_mode, source_modes))

