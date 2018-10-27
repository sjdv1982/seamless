import json
from ...mixed import MixedScalar

def seamless_encoder(obj):
    if isinstance(obj, MixedScalar):
        return default_encoder.encode(obj.value)
    else:
        raise TypeError(repr(obj) + " is not JSON serializable")

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
