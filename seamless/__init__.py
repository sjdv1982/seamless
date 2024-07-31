"""Seamless: a framework for reusable computations and interactive workflows

Author: Sjoerd de Vries
Copyright 2016-2024, INSERM, CNRS and project contributors
"""

__version__ = "0.13"


import logging

logger = logging.getLogger(__name__)

class CacheMissError(Exception):
    """Exception for when a checksum cannot be mapped to a buffer"""
    pass

from silk import Silk
from .Checksum import Checksum
from .Buffer import Buffer
from . import config
from . import multi
from seamless.config import delegate
from seamless.direct import transformer
from seamless.util import fair
__all__ = [
    "Silk", "Checksum", "Buffer", "config", 
    "CacheMissError", "transformer", "delegate", "multi", "fair",
]