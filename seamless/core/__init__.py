"""Deprecation stub"""

import warnings
import seamless.workflow.core
from seamless.workflow.core import *

warnings.warn(
    "seamless.core is deprecated. Use seamless.workflow.core instead.",
    DeprecationWarning,
    2,
)

__all__ = list(dir(seamless.workflow.core))
