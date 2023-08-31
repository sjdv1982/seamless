from requests.exceptions import ConnectionError

from seamless.util import parse_checksum

def has(session, url, checksum):
    checksum = parse_checksum(checksum)
    assert checksum is not None
    path = url + "/has"
    response = session.get(path, json=[checksum])        
    if int(response.status_code/100) in (4,5):
        raise ConnectionError()
    result = response.json()
    if not isinstance(result, list) or len(result) != 1:
            raise ValueError(result)
    if not isinstance(result[0], bool):
            raise ValueError(result)
    return result[0]

def write(session, url, checksum, buffer:bytes):
    checksum = parse_checksum(checksum)
    assert checksum is not None
    path = url + "/" + checksum
    response = session.put(path, data=buffer)
    if int(response.status_code/100) in (4,5):
        raise ConnectionError()
