from functools import partial, update_wrapper

class SelfWrapper:
    """Wraps class attributes that could be overruled by instance attributes"""
    def __init__(self, wrapped, attributelist):
        self._attributelist = attributelist
        self._wrapped = wrapped
        self._cls = type(wrapped)
    def __getattr__(self, attr):
        if attr not in self._attributelist:
            raise AttributeError(attr)
        prop = self._cls.__dict__[attr]
        if callable(prop):
            wprop = partial(prop, self._wrapped)
            update_wrapper(wrapped=prop, wrapper=wprop)
            return wprop
        elif isinstance(prop, property):
            return prop.fget(self._wrapped)
        else:
            return prop