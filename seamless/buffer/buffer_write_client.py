"""Client to a remote buffer write server"""

import requests
from requests.exceptions import (  # pylint: disable=redefined-builtin
    ConnectionError,
    ChunkedEncodingError,
    JSONDecodeError,
)
from seamless import Checksum


def has(session, url, checksum: Checksum, *, timeout=None):
    from seamless.workflow.util import is_forked

    sess = session
    if is_forked():
        sess = requests
    checksum = Checksum(checksum)
    assert checksum
    path = url + "/has"
    result = None
    for _trial in range(10):
        try:
            with sess.get(path, json=[checksum], timeout=timeout) as response:
                if int(response.status_code / 100) in (4, 5):
                    raise ConnectionError()
                result = response.json()
        except ChunkedEncodingError:
            continue
        except JSONDecodeError:
            continue
        except ConnectionError as exc:
            if not exc.args or not isinstance(exc.args[0], Exception):
                raise exc from None
            if not exc.args[0].args or exc.args[0].args[0] != "Connection aborted.":
                raise exc from None
            continue
        break

    if not isinstance(result, list) or len(result) != 1:
        raise ValueError(result)
    if not isinstance(result[0], bool):
        raise ValueError(result)
    return result[0]


def write(session, url, checksum: Checksum, buffer: bytes):
    from seamless.workflow.util import is_forked

    sess = session
    if is_forked():
        sess = requests
    checksum = Checksum(checksum)
    assert checksum
    path = url + "/" + checksum
    for _trial in range(10):
        try:
            with sess.put(path, data=buffer) as response:
                if int(response.status_code / 100) in (4, 5):
                    raise ConnectionError(
                        f"Error {response.status_code}: {response.text}"
                    )
            break
        except ChunkedEncodingError:
            continue
        except ConnectionError as exc:
            if not exc.args or not isinstance(exc.args[0], Exception):
                raise exc from None
            if not exc.args[0].args or exc.args[0].args[0] != "Connection aborted.":
                raise exc from None
            continue
