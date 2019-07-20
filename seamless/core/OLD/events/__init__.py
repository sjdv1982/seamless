print("events/__init__.py: change of plan => abolish events")

from .. import protocol
from ..protocol.deserialize import deserialize
from ..cache import (CellCache, AccessorCache, ExpressionCache, ValueCache,
    TransformCache, LabelCache, Accessor, Expression, TempRefManager, SemanticKey,
    CacheMissError)

class Event:
    def process(self, manager):
        raise NotImplementedError

from .eventloop import EventLoop