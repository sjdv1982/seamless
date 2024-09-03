"""Deprecation stub"""

import warnings
import seamless.workflow
from seamless import Checksum, Buffer, CacheMissError
from seamless.workflow import *
from seamless.workflow.highlevel import stdlib

warnings.warn(
    "seamless.highlevel is deprecated. Use seamless.workflow instead.",
    DeprecationWarning,
    2,
)

__all__ = seamless.workflow.__all__ + ["Checksum", "Buffer", "CacheMissError", "stdlib"]
