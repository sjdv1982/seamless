from multiprocessing import current_process
try:
    from multiprocessing import parent_process
except ImportError:
    parent_process = None

def parse_checksum(checksum, as_bytes=False):
    """Parses checksum and returns it as string
If as_bytes is True, return it as bytes instead."""
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


def is_forked():
    if parent_process is None:  # Python 3.7
        if current_process().name != "MainProcess":  # forked process
            return True
    else:
        if parent_process() is not None:  # forked process
            return True
    return False
