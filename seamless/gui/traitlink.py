import traitlets
from collections import namedtuple
import traceback

def traitlink(c, t):
    assert isinstance(c, seamless.core.Cell)
    assert isinstance(t, tuple) and len(t) == 2
    assert isinstance(t[0], traitlets.HasTraits)
    assert t[0].has_trait(t[1])
    handler = lambda d: c.set(d["new"])
    value = c.value
    if value is not None:
        setattr(t[0], t[1], value)
    else:
        c.set(getattr(t[0], t[1]))
    def set_traitlet(value):
        try:
            setattr(t[0], t[1], value)
        except:
            traceback.print_exc()
    t[0].observe(handler, names=[t[1]])
    obs = seamless.observer(c, set_traitlet )
    result = namedtuple('Traitlink', ["unobserve"])
    def unobserve():
        nonlocal obs
        t[0].unobserve(handler)
        del obs
    result.unobserve = unobserve
    return result
