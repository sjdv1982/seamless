import traitlets
from collections import namedtuple
import traceback

def widgetlink(c, w, as_data=False):
    from ..core import Cell
    from .. import observer
    assert isinstance(c, Cell)
    assert isinstance(w, traitlets.HasTraits)
    assert w.has_trait("value")
    handler = lambda d: c.set(d["new"])
    value = c.data if as_data else c.value
    if value is not None:
        w.value = value
    else:
        c.set(w.value)
    def set_traitlet(value):
        try:
            w.value = value
        except:
            traceback.print_exc()
    w.observe(handler, names=["value"])
    obs = observer(c, set_traitlet, as_data = as_data )
    result = namedtuple('Widgetlink', ["unobserve"])
    def unobserve():
        nonlocal obs
        t[0].unobserve(handler)
        del obs
    result.unobserve = unobserve
    return result
