# pylint: disable=wrong-import-position
"""Seamless: a framework for reusable computations and interactive workflows

# Author: Sjoerd de Vries
# Copyright (c) 2016-2024, INSERM, CNRS and project contributors

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
"""

__version__ = "0.14"


import logging

logger = logging.getLogger(__name__)

SEAMLESS_WORKFLOW_IMPORTED = False


class CacheMissError(Exception):
    """Exception for when a checksum cannot be mapped to a buffer"""


from seamless.Checksum import Checksum
from seamless.Buffer import Buffer
from seamless.config import delegate
from seamless.direct import transformer, run_transformation
from seamless.util import fair
from . import config
from . import multi

__all__ = [
    "Checksum",
    "Buffer",
    "config",
    "CacheMissError",
    "transformer",
    "delegate",
    "multi",
    "fair",
    "run_transformation",
]
