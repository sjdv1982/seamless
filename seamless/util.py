import json
from multiprocessing import current_process
try:
    from multiprocessing import parent_process
except ImportError:
    parent_process = None

def parse_checksum(checksum, as_bytes=False):
    """Parses checksum and returns it as string
If as_bytes is True, return it as bytes instead."""
    from seamless.highlevel import Checksum
    if isinstance(checksum, Checksum):
        checksum = checksum.bytes()
    if isinstance(checksum, bytes):
        checksum = checksum.hex()
    if isinstance(checksum, str):
        checksum = bytes.fromhex(checksum)

    if isinstance(checksum, bytes):
        if len(checksum) != 32:
            raise ValueError(f"Incorrect length: {len(checksum)}, must be 32")
        if as_bytes:
            return checksum
        else:
            return checksum.hex()
    
    if checksum is None:
        return
    raise TypeError(type(checksum))

def as_tuple(v):
    if isinstance(v, str):
        return (v,)
    else:
        return tuple(v)

def strip_decorators(code):
    lines = code.splitlines()
    lnr = 0
    for lnr, l in enumerate(lines):
        if not l.startswith("@"):
            break
    return "\n".join(lines[lnr:])

def ast_dump(node, annotate_fields=True, include_attributes=False, *, indent=None):
    """
    From the CPython 3.10 source code, https://github.com/python/cpython/blob/3.10/Lib/ast.py
    :copyright: Copyright 2008 by Armin Ronacher.
    :license: Python License.

    Return a formatted dump of the tree in node.  This is mainly useful for
    debugging purposes.  If annotate_fields is true (by default),
    the returned string will show the names and the values for fields.
    If annotate_fields is false, the result string will be more compact by
    omitting unambiguous field names.  Attributes such as line
    numbers and column offsets are not dumped by default.  If this is wanted,
    include_attributes can be set to true.  If indent is a non-negative
    integer or string, then the tree will be pretty-printed with that indent
    level. None (the default) selects the single line representation.
    """
    from ast import AST
    def _format(node, level=0):
        if indent is not None:
            level += 1
            prefix = '\n' + indent * level
            sep = ',\n' + indent * level
        else:
            prefix = ''
            sep = ', '
        if isinstance(node, AST):
            cls = type(node)
            args = []
            allsimple = True
            keywords = annotate_fields
            for name in node._fields:
                try:
                    value = getattr(node, name)
                except AttributeError:
                    keywords = True
                    continue
                if value is None and getattr(cls, name, ...) is None:
                    keywords = True
                    continue
                value, simple = _format(value, level)
                allsimple = allsimple and simple
                if keywords:
                    args.append('%s=%s' % (name, value))
                else:
                    args.append(value)
            if include_attributes and node._attributes:
                for name in node._attributes:
                    try:
                        value = getattr(node, name)
                    except AttributeError:
                        continue
                    if value is None and getattr(cls, name, ...) is None:
                        continue
                    value, simple = _format(value, level)
                    allsimple = allsimple and simple
                    args.append('%s=%s' % (name, value))
            if allsimple and len(args) <= 3:
                return '%s(%s)' % (node.__class__.__name__, ', '.join(args)), not args
            return '%s(%s%s)' % (node.__class__.__name__, prefix, sep.join(args)), False
        elif isinstance(node, list):
            if not node:
                return '[]', True
            return '[%s%s]' % (prefix, sep.join(_format(x, level)[0] for x in node)), False
        return repr(node), True

    if not isinstance(node, AST):
        raise TypeError('expected AST, got %r' % node.__class__.__name__)
    if indent is not None and not isinstance(indent, str):
        indent = ' ' * indent
    return _format(node)[0]


_unforked_process_name = None
def set_unforked_process():
    """Sets the current process as the unforked Seamless process"""
    global _unforked_process_name
    _unforked_process_name = current_process().name

def is_forked():
    if _unforked_process_name:
        if current_process().name != _unforked_process_name:
            return True
    elif parent_process is None:  # Python 3.7
        if current_process().name != "MainProcess":  # forked process
            return True
    else:
        if parent_process() is not None:  # forked process
            return True
    return False

def verify_transformation_success(transformation_checksum, transformation_dict=None):
    from .highlevel import Checksum
    from .config import database
    from .core.cache.buffer_cache import buffer_cache
    from .core.manager.expression import Expression
    assert database.active
    if transformation_checksum is None:
        return None
    tf_checksum = Checksum(transformation_checksum)
    if transformation_dict is None:
        tf_buffer = buffer_cache.get_buffer(tf_checksum.hex())
        if tf_buffer is None:
            return None

        transformation_dict = json.loads(tf_buffer.decode( ))
    assert isinstance(transformation_dict, dict)
    language = transformation_dict["__language__"]
    if language == "<expression>":
        expression_dict = transformation_dict["expression"]
        d = expression_dict.copy()
        d["target_subcelltype"] = None
        d["hash_pattern"] = d.get("hash_pattern")
        d["target_hash_pattern"] = d.get("target_hash_pattern")
        d["checksum"] = bytes.fromhex(d["checksum"])
        expression = Expression(**d)
        #print("LOOK FOR EXPRESSION", expression.checksum.hex(), expression.path)
        result = database.get_expression(expression)
        #print("/LOOK FOR EXPRESSION", expression.checksum.hex(), expression.path, parse_checksum(result) )
        return result
    elif language == "<structured_cell_join>":
        join_dict = transformation_dict["structured_cell_join"].copy()
        inchannels0 = join_dict.get("inchannels", {})
        inchannels = {}
        for path0, cs in inchannels0.items():
            path = json.loads(path0)
            if isinstance(path, list):
                path = tuple(path)
            inchannels[path] = cs
        from seamless import calculate_dict_checksum
        #print("LOOK FOR SCELL JOIN", calculate_dict_checksum(join_dict,hex=True))
        result = database.get_structured_cell_join(join_dict)
        #print("/LOOK FOR SCELL JOIN", calculate_dict_checksum(join_dict,hex=True), parse_checksum(result))
        return result
    else:
        #print("LOOK FOR TRANSFORMATION", transformation_checksum)
        result = database.get_transformation_result(transformation_checksum.bytes())
        #print("/LOOK FOR TRANSFORMATION", transformation_checksum)
        return result

