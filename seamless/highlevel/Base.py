# Author: Sjoerd de Vries
# Copyright (c) 2016-2022 INSERM, 2022 CNRS

# The MIT License (MIT)

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Base class for Context and all possible Context children."""

from __future__ import annotations
from typing import *
import weakref


class Base:
    """Base class of all Seamless highlevel objects that can be in a Context"""
    _parent: Any  # weakref.ref or lambda returning None
    _parent = lambda self: None
    if TYPE_CHECKING:
        from .Context import Context

    def _get_parent(self) -> Context:
        result = self._parent()
        assert result is not None
        return result

    _path: Optional[tuple[str, ...]] = None

    def _get_path(self) -> tuple[str, ...]:
        result = self._path
        assert result is not None
        return result


    def __init__(self, parent, path):
        assert (parent is None) == (path is None or not len(path))
        if parent is not None:
            self._init2(parent, path)
    
    def _init2(self, parent, path):
        from .Context import Context

        if parent is not None:
            assert isinstance(parent, Context)
            if parent._weak:
                self._parent = lambda: parent
            else:
                self._parent = weakref.ref(parent)
        if isinstance(path, str):
            path = (path,)
        self._path = path

    def _get_top_parent(self):
        from .Context import Context

        parent = self._parent()
        if isinstance(parent, Context):
            return parent
        else:
            return parent._get_parent()

    @property
    def path(self) -> str:
        """Return path as a string"""
        if self._path is None:
            return "<None>"
        return "." + ".".join(self._path)
