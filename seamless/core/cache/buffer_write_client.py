from requests.exceptions import ConnectionError, ChunkedEncodingError, JSONDecodeError

from seamless.util import parse_checksum

def has(session, url, checksum):
    checksum = parse_checksum(checksum)
    assert checksum is not None
    path = url + "/has"
    for trial in range(10):
        try:
            with session.get(path, json=[checksum]) as response:
                if int(response.status_code/100) in (4,5):
                    raise ConnectionError()
                result = response.json()
        except ChunkedEncodingError:
             continue
        except JSONDecodeError:
             continue
        except ConnectionError as exc:
             if not exc.args or not isinstance(exc.args[0], Exception):
                raise exc from None
             if not exc.args[0].args or exc.args[0].args[0] != 'Connection aborted.':
                raise exc from None
             continue
        break

    if not isinstance(result, list) or len(result) != 1:
        raise ValueError(result)
    if not isinstance(result[0], bool):
        raise ValueError(result)
    return result[0]

def write(session, url, checksum, buffer:bytes):
    checksum = parse_checksum(checksum)
    assert checksum is not None
    path = url + "/" + checksum
    for trial in range(10):
        try:
            with session.put(path, data=buffer) as response:
                if int(response.status_code/100) in (4,5):
                    raise ConnectionError()
            break
        except ChunkedEncodingError:
             continue
        except ConnectionError as exc:
             if not exc.args or not isinstance(exc.args[0], Exception):
                raise exc from None
             if not exc.args[0].args or exc.args[0].args[0] != 'Connection aborted.':
                raise exc from None
             continue
