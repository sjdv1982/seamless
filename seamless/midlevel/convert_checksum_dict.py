
def convert_checksum_dict(checksum_dict, prefix):
    """
    Convert highlevel checksum dict keys to checksum dict keys that a structured cell expects
    """
    is_legacy = False
    result = {}
    for k in checksum_dict:
        if k == "schema":
            result[k] = checksum_dict[k]
            continue
        if not k.startswith(prefix):
            continue
        k2 = "value" if k == prefix else k[len(prefix+"_"):]
        if k2 == "auth" and checksum_dict[k] == 'd0a1b2af1705c1b8495b00145082ef7470384e62ac1c4d9b9cdbbe0476c28f8c': #{}
            continue
        """
        if k2 == "auth":
            unconverted_checksum = checksum_dict[k]
            is_legacy, converted_checksum = check_and_convert_legacy(unconverted_checksum)
            if is_legacy:
                result[k2] = converted_checksum
                continue
        """
        result[k2] = checksum_dict[k]
    if is_legacy:
        for k in list(result.keys()):
            if k != "schema":
                if result[k] == converted_checksum:
                    pass
                elif result[k] == unconverted_checksum:
                    result[k] = converted_checksum
                else:
                    result.pop(k)
    return result

from ..core.cache.buffer_cache import buffer_cache, CacheMissError
from silk.mixed.io import deserialize as mixed_deserialize
from ..core.protocol.serialize import serialize_sync
from ..core.protocol.deep_structure import value_to_deep_structure_sync
from ..core.protocol.calculate_checksum import calculate_checksum_sync