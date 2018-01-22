from numpy import ndarray, void
from . import MixedBase

class MixedDict(MixedBase):
    def __init__(self, data, form = None):
        if not isinstance(data, dict):
            raise TypeError
        self._data = data
        if form is None:
            form = self._get_form(data)
        self._form = form

    def _get_form(self, data):
        if isinstance(data, void):

        if isinstance(data, ndarray):
            
