from requests.exceptions import ConnectionError, ReadTimeout

from seamless.util import parse_checksum

def has(session, url, checksum):
    checksum = parse_checksum(checksum)
    assert checksum is not None
    try:
        path = url + "/has"
        with session.get(path, json=[checksum]) as response:
            if int(response.status_code/100) in (4,5):
                raise ConnectionError()
            result = response.json()
        if not isinstance(result, list) or len(result) != 1:
             raise ValueError(result)
        if not isinstance(result[0], bool):
             raise ValueError(result)
        return result[0]
    except (ConnectionError, ReadTimeout):
        #import traceback; traceback.print_exc()
        return
    except Exception:
        import traceback; traceback.print_exc()
        return

def get(session, url, checksum):
    checksum = parse_checksum(checksum)
    assert checksum is not None
    try:
        path = url + "/" + checksum
        with session.get(path, stream=True, timeout=3) as response:
            if int(response.status_code/100) in (4,5):
                raise ConnectionError()
            result = []
            for chunk in response.iter_content(100000):
                result.append(chunk)
        buf = b"".join(result)
        from seamless import calculate_checksum
        buf_checksum = calculate_checksum(buf, hex=True)
        if buf_checksum != checksum:
            #print("WARNING: '{}' has the wrong checksum".format(url))
            return
    except (ConnectionError, ReadTimeout):
        #import traceback; traceback.print_exc()
        return
    except Exception:
        import traceback; traceback.print_exc()
        return

    return buf
