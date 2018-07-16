from ..mixed import MixedBase
from ..silk import Silk
from ..silk.validation import _allowed_types

ConstantTypes = _allowed_types + (Silk, MixedBase, tuple)

from .Context import Context
