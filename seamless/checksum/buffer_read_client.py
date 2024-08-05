"""Client to a remote buffer write server"""

import sys
import requests
from requests.exceptions import (  # pylint: disable=redefined-builtin
    ConnectionError,
    ReadTimeout,
)

from seamless import Buffer, Checksum
from seamless.util.is_forked import is_forked


def has(session: requests.Session, url: str, checksum: Checksum) -> bool:
    """Check if a buffer is available at a remote URL.
    URL is accessed using HTTP GET, with /has added to the URL,
     and the checksum as parameter"""

    sess = session
    if is_forked():
        sess = requests
    checksum = Checksum(checksum)
    assert checksum
    try:
        path = url + "/has"
        with sess.get(path, json=[checksum]) as response:
            if int(response.status_code / 100) in (4, 5):
                raise ConnectionError()
            result = response.json()
        if not isinstance(result, list) or len(result) != 1:
            raise ValueError(result)
        if not isinstance(result[0], bool):
            raise ValueError(result)
        return result[0]
    except (ConnectionError, ReadTimeout):
        # import traceback; traceback.print_exc()
        return
    except Exception:
        import traceback

        traceback.print_exc()
        return


def get(session: requests.Session, url: str, checksum: Checksum) -> bytes | None:
    """Download a buffer from a remote URL.
    URL is accessed using HTTP GET, with /<checksum> added to the URL"""

    sess = session
    if is_forked():
        sess = requests
    checksum = Checksum(checksum)
    assert checksum
    curr_buf_checksum = None
    while 1:
        try:
            path = url + "/" + checksum
            with sess.get(path, stream=True, timeout=10) as response:
                if int(response.status_code / 100) in (4, 5):
                    raise ConnectionError()
                result = []
                for chunk in response.iter_content(100000):
                    result.append(chunk)
            buf = b"".join(result)
            buf_checksum = Buffer(buf).get_checksum().value
            if buf_checksum != checksum:
                if buf_checksum != curr_buf_checksum:
                    curr_buf_checksum = buf_checksum
                    continue
                print(
                    "WARNING: '{}' has the wrong checksum for {}".format(url, checksum),
                    file=sys.stderr,
                )
                return
            break
        except (ConnectionError, ReadTimeout):
            # import traceback; traceback.print_exc()
            return
        except Exception:
            import traceback

            traceback.print_exc()
            return

    return buf
