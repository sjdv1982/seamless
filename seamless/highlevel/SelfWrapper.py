from functools import partial, update_wrapper

class SelfWrapper:
    """Wraps class attributes that could be overruled by instance attributes"""
    _ATTRIBUTES = "Attributes"
    def __init__(self, wrapped, attributelist):
        self._attributelist = attributelist
        self._wrapped = wrapped
        self._cls = type(wrapped)

    def _get_prop(self, attr):
        try:
            return self._cls.__dict__[attr]
        except KeyError:
            for base in self._cls.__bases__:
                try:
                    return base.__dict__[attr]
                except KeyError:
                    pass
            raise KeyError(attr) from None

    def __getattr__(self, attr):
        if attr not in self._attributelist:
            raise AttributeError(attr)
        prop = self._get_prop(attr)
        if callable(prop):
            wprop = partial(prop, self._wrapped)
            update_wrapper(wrapped=prop, wrapper=wprop)
            return wprop
        elif isinstance(prop, property):
            return prop.fget(self._wrapped)
        else:
            return prop

    def __dir__(self):
        return self._attributelist

    def __str__(self):
        return self._ATTRIBUTES + " of " + str(self._wrapped)

    def __repr__(self):
        return str(self)

class ChildrenWrapper(SelfWrapper):
    _ATTRIBUTES = "Children"

    def _get_prop(self, attr):
        return self._wrapped._get_from_path((attr,))
    