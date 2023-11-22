import sys
from requests.exceptions import ConnectionError, ReadTimeout

from seamless.util import parse_checksum, is_forked

def has(session, url, checksum):
    assert not is_forked()
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
    assert not is_forked()
    checksum = parse_checksum(checksum)
    assert checksum is not None
    curr_buf_checksum = None
    while 1:
        try:
            path = url + "/" + checksum
            with session.get(path, stream=True, timeout=10) as response:
                if int(response.status_code/100) in (4,5):
                    raise ConnectionError()
                result = []
                for chunk in response.iter_content(100000):
                    result.append(chunk)
            buf = b"".join(result)
            from seamless import calculate_checksum
            buf_checksum = calculate_checksum(buf, hex=True)
            if buf_checksum != checksum:
                if buf_checksum != curr_buf_checksum:
                    curr_buf_checksum = buf_checksum
                    continue
                print("WARNING: '{}' has the wrong checksum for {}".format(url, checksum), file=sys.stderr)
                return
            break
        except (ConnectionError, ReadTimeout):
            #import traceback; traceback.print_exc()
            return
        except Exception:
            import traceback; traceback.print_exc()
            return

    return buf
