import weakref

from . import SeamlessBase

class Inchannel:
    def __init__(self, structured_cell, name):
        assert isinstance(name, tuple)
        self.structured_cell = weakref.ref(structured_cell)
        self.name = name

class Outchannel:
    def __init__(self, structured_cell, name):
        assert isinstance(name, tuple)
        self.structured_cell = weakref.ref(structured_cell)
        self.name = name

class Editchannel:
    def __init__(self, structured_cell, name):
        assert isinstance(name, tuple)
        self.structured_cell = weakref.ref(structured_cell)
        self.name = name

class StructuredCell(SeamlessBase):
    _celltype = "structured"
    def __init__(self, data, *,
        auth=None,
        schema=None,
        inchannels=None,
        outchannels=None,
        editchannels=None,
        buffer=None
    ):
        raise NotImplementedError # livegraph branch


    def _set_observer(self, observer, trigger=True):
        self.data._set_observer(observer, trigger)

    def _add_traitlet(self, traitlet, trigger=True):
        self.data._add_traitlet(traitlet)

    def _set_context(self, context, name):
        has_ctx = self._context is not None
        super()._set_context(ctx, name)
        assert self._context() is ctx
        manager = self._get_manager()
        if not has_ctx:
            manager.register_structured_cell(self)
