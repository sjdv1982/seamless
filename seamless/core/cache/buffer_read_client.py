from requests.exceptions import ConnectionError, ReadTimeout

from seamless.util import parse_checksum

def get(session, url, checksum):
    checksum = parse_checksum(checksum)
    assert checksum is not None
    try:
        path = url + "/" + checksum
        response = session.get(path, stream=True, timeout=3)        
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

from .buffer_write_client import has