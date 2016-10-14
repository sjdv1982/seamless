import logging
from .context import register_subcontext_factory
from .cell import Cell, cell, pythoncell
from .process import Process

# Module logger
logger = logging.getLogger(__name__)

# Initialise subcontexts
register_subcontext_factory("processes", "process{}", capturing_class=Process, constructor=None)
register_subcontext_factory("cells", "cell{}", capturing_class=Cell, constructor=cell)
register_subcontext_factory("cells.python", "pythoncell{}", capturing_class=None, constructor=pythoncell)
