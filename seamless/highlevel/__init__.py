"""Seamless high-level API.

Has a two-fold function:

1. Maintain a workflow graph containing nodes (cells, transformers etc.),
checksums, and connections. This workflow graph is pure data that can be
serialized any time to JSON (.seamless file).

2. Maintain a translation of the workflow graph to a low-level representation
that is constantly being evaluated. Interrogate the low-level representation
(asking for its status, checksums, etc.).
"""
import inspect
from types import LambdaType
from ast import PyCF_ONLY_AST, FunctionDef, Expr, Lambda
import textwrap

from silk.mixed import MixedBase
from silk import Silk
from silk.validation import _allowed_types
from ..core.lambdacode import lambdacode
from ..core.cached_compile import cached_compile

ConstantTypes = _allowed_types + (Silk, MixedBase, tuple)

import inspect
import os

def set_resource(f):
    caller_frame = inspect.currentframe().f_back
    filename = os.path.realpath(inspect.getfile(caller_frame))
    currdir = os.path.realpath(os.getcwd())
    if filename.startswith(currdir):
        filename = os.path.relpath(filename, currdir)
    dirname = os.path.dirname(filename)
    ff = os.path.join(dirname, f)
    if inspect.getmodule(caller_frame).__name__ == "__main__":
        return Resource(ff)
    else:
        data = open(ff).read()
        return data

def parse_function_code(code_or_func, identifier="<None>"):
    from ..util import strip_decorators
    if callable(code_or_func):
        func = code_or_func
        code = inspect.getsource(func)
        if code is not None:
            code = textwrap.dedent(code)
            code = strip_decorators(code)
        if isinstance(func, LambdaType) and func.__name__ == "<lambda>":
            code = lambdacode(func)
            if code is None:
                raise ValueError("Cannot extract source code from this lambda")
    else:
        assert isinstance(code_or_func, str)
        code = code_or_func

    ast = cached_compile(code, identifier, "exec", PyCF_ONLY_AST)
    is_function = (len(ast.body) == 1 and
                   isinstance(ast.body[0], FunctionDef))

    if is_function:
        func_name = ast.body[0].name
        code_object = cached_compile(code, identifier, "exec")
    else:
        assert (len(ast.body) == 1 and isinstance(ast.body[0], Expr))
        assert isinstance(ast.body[0].value, Lambda)
        func_name = "<lambda>"
        code_object = cached_compile(code, identifier, "eval")
    return code, func_name, code_object

from .Context import Context
from .Transformer import Transformer
from .Macro import Macro
from .Cell import Cell, SimpleDeepCell, FolderCell
from .DeepCell import DeepCell, DeepFolderCell
from .Module import Module
from .Link import Link
from .Resource import Resource
from ..midlevel.StaticContext import StaticContext
from .copy import copy

def load_graph(graph, *, zip=None, cache_ctx=None, static=False, mounts=True, shares=True):
    """Load a Context from graph.

    "graph" can be a file name or a JSON dict
    Normally, it has been generated with Context.save_graph / Context.get_graph

    "zip" can be a file name, zip-compressed bytes or a Python ZipFile object.
    Normally, it has been generated with Context.save_zip / Context.get_zip

    "cache_ctx": re-use a previous context for caching (e.g. checksum-to-buffer caching)

    "static": create a StaticContext instead

    "mounts": mount cells and pins to the file system, as specified in the graph.

    "shares": share cells over HTTP, as specified in the graph
    """
    import json
    from ..core.context import Context as CoreContext
    from ..core.manager import Manager
    from ..core.unbound_context import UnboundManager
    if isinstance(graph, str):
        graph = json.load(open(graph))
    if isinstance(cache_ctx, Context):
        manager = cache_ctx._ctx0._get_manager()
    elif isinstance(cache_ctx, CoreContext):
        manager = cache_ctx._get_manager()
    elif isinstance(cache_ctx, (Manager, UnboundManager)):
        manager = cache_ctx
    elif cache_ctx is None:
        manager = None
    else:
        raise TypeError(cache_ctx)
    if isinstance(manager, UnboundManager):
        manager = manager._ctx._bound._get_manager()
        assert isinstance(manager, Manager)
    if static:
        return StaticContext.from_graph(graph, manager=manager)
    else:
        return Context.from_graph(
            graph, manager=manager,
            mounts=mounts, shares=shares,
            zip=zip
        )

class Checksum:
    def __init__(self, checksum):
        from seamless import parse_checksum
        self.value = parse_checksum(checksum, as_bytes=False)
    
    def bytes(self) -> bytes | None:
        if self.value is None:
            return None
        return bytes.fromhex(self.value)
    
    def __str__(self):
        return str(self.value)

from .SubContext import SubContext
from .Base import Base
nodeclasses = {
    "cell": Cell,
    "transformer": Transformer,
    "context": SubContext,
    "macro": Macro,
    "module": Module,
    "foldercell": FolderCell,
    "deepcell": DeepCell,
    "deepfoldercell": DeepFolderCell,
}

__all__ = [
    "Context", "Transformer", "Macro",
    "Cell", "SimpleDeepCell", "FolderCell", "DeepCell", "DeepFolderCell",
    "Link", "StaticContext", "Module", "Checksum",
    "Resource", "load_graph", "copy"
]

def __dir__():
    return sorted(__all__)
