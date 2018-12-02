import json
import numpy as np
from ...mixed import MixedScalar
from ...silk.validation import _integer_types, _float_types
def seamless_encoder(obj):
    from ..structured_cell import StructuredCellState
    retry = False
    if isinstance(obj, MixedScalar):
        obj = obj.value
        retry = True
    if isinstance(obj, np.generic):
        if isinstance(obj, _integer_types):
            obj = int(obj)
            retry = True
        elif isinstance(obj, _float_types):
            obj = float(obj)
            retry = True
    """
    elif isinstance(obj, StructuredCellState):
        result = {}
        for k in [k for k in dir(StructuredCellState) if getattr(StructuredCellState,k) in (False, None)]:
            v = getattr(obj, k)
            try:
                vv = default_encoder.encode(v)
            except TypeError:
                vv = seamless_encoder(v)
            result[k] = vv
        return result
    """
    if retry:
        return default_encoder.encode(obj)
    else:
        typename = obj.__class__.__name__
        raise TypeError("%s object %s is not JSON serializable" % (typename, repr(obj)))

def json_encode(obj, *, skipkeys=False, ensure_ascii=True, check_circular=True,
        allow_nan=True, cls=None, indent=None, separators=None,
        default=seamless_encoder, sort_keys=False, **kw):
    """Serialize ``obj`` to a JSON formatted ``str``.

    Wrapper around json.dumps that overrides the default value of "default"
    """
    global default_encoder
    default_encoder = json.JSONEncoder(
      skipkeys=skipkeys,
      ensure_ascii=ensure_ascii,
      check_circular=check_circular,
      allow_nan=allow_nan,
      indent=indent,
      separators=separators,
      default=None,
      sort_keys=sort_keys,
      **kw
    )
    return json.dumps(obj,
      skipkeys=skipkeys,
      ensure_ascii=ensure_ascii,
      check_circular=check_circular,
      allow_nan=allow_nan,
      cls=cls,
      indent=indent,
      separators=separators,
      default=default,
      sort_keys=sort_keys,
      **kw
    )
