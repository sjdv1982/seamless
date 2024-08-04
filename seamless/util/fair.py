"""
Seamless support for FAIR principles
(Findable, Accessible, Interoperable, Reusable)

Client for a Seamless fairserver.
"""

import json
import sys
import urllib.parse
from requests.exceptions import (  # pylint: disable=redefined-builtin
    ConnectionError,
    ReadTimeout,
)

from seamless import Checksum
from seamless.checksum.download_buffer import (
    download_buffer_sync,
    validate_url_info,
    session,
)

_servers = []
_direct_urls = {}


def get_servers():
    """Get list of FAIR servers"""
    return _servers.copy()


def add_server(url):
    """Add FAIR server"""
    _servers.append(url)


def add_direct_urls(url_info_dict):
    """A dict where the keys are checksums and the values are (a single or a list of) url infos.
    An url info can be a URL string or a dict containing 'url' and
    optionally 'celltype', 'compression'.
    """
    for cs, url_infos in url_info_dict.items():
        if isinstance(url_infos, (dict, str)):
            url_infos = [url_infos]
        checksum = Checksum(cs)
        for url_info in url_infos:
            validate_url_info(url_info)
            if checksum not in _direct_urls:
                _direct_urls[checksum] = []
            _direct_urls[checksum].append(url_info)


_classification = {
    "bytes_item": set(),
    "mixed_item": set(),
    "keyorder": set(),
}


def _classify(checksum: Checksum, classification: str):
    checksum = Checksum(checksum)
    if classification not in ("bytes_item", "mixed_item", "keyorder"):
        raise ValueError(classification)
    _classification[classification].add(checksum)


def _download(
    checksum: Checksum, template, *, checksum_content: bool, verbose: bool = False
):
    from seamless.checksum.get_buffer import get_buffer as get_buffer0

    checksum = Checksum(checksum)
    if not checksum:
        return None
    request = template + checksum.hex()
    urls = [urllib.parse.urljoin(server, request) for server in _servers]
    if checksum_content:
        result = get_buffer0(checksum, remote=False)
        if result is None:
            result = download_buffer_sync(checksum, urls, verbose=verbose)
        if result is None:
            result = get_buffer0(checksum, remote=True)
    else:
        result = download_buffer_sync(None, urls, verbose=verbose)
    return result


def get_dataset(dataset: str):
    """Download dataset metadata"""
    request = "/machine/dataset/{}".format(dataset)
    urls = [urllib.parse.urljoin(server, request) for server in _servers]
    datasetbuffer = download_buffer_sync(None, urls)
    if datasetbuffer is not None:
        return json.loads(datasetbuffer.decode())


def find(checksum: Checksum):
    """Find a distribution (and its dataset) by its checksum"""
    checksum = Checksum(checksum)
    if not checksum:
        return None
    request = "/machine/find/" + checksum
    urls = [urllib.parse.urljoin(server, request) for server in _servers]
    for url in urls:
        try:
            response = session.get(url, timeout=3)
            if int(response.status_code / 100) in (4, 5):
                # raise Exception(response.text + ": " + checksum)
                continue
            else:
                return response.json()
        except (ConnectionError, ReadTimeout):
            continue
    raise ConnectionError("Cannot contact any FAIR server")


def keyorder(checksum: str, verbose: bool = False) -> list | None:
    """Get the keyorder list that corresponds to a data distribution (i.e. deepcell).
    The checksum is that of the distribution."""
    return _download(
        checksum, "machine/keyorder/", checksum_content=False, verbose=verbose
    )


def access(checksum: Checksum, celltype: str, *, verbose: bool = False) -> bytes | None:
    """Download the buffer of a checksum.
    First, retrieve  its associated URL info metadata.
    Use those URLs to download the content.
    The checksum of the content is verified."""
    from seamless.checksum.get_buffer import get_buffer as get_buffer0

    checksum = Checksum(checksum)
    result = get_buffer0(checksum, remote=False)
    if result is not None:
        return result
    url_infos_buf = _download(
        checksum, "machine/access/", checksum_content=False, verbose=verbose
    )
    if url_infos_buf is None:
        return None
    url_infos = json.loads(url_infos_buf.decode())
    result = download_buffer_sync(checksum, url_infos, celltype, verbose=verbose)
    if result is None:
        if verbose:
            print("Try remote buffer cache...", file=sys.stderr)
            sys.stderr.flush()
        result = get_buffer0(checksum, remote=True)
    return result


def get_buffer(checksum: Checksum, deep=False):
    """Download the buffer of a checksum.
    Various mechanisms are tried:
    - Direct download via known URLs.
    - Download from known URLs using the FAIR server "access" API.
    - Try if it is a keyorder buffer,
    in which case it can be downloaded directly from the FAIR server.
    """
    checksum = Checksum(checksum)
    if not checksum:
        return None
    if checksum in _direct_urls:
        buffer = download_buffer_sync(checksum, _direct_urls[checksum])
        if buffer is not None:
            return buffer
    for c, cc in _classification.items():
        if checksum in cc:
            if c == "bytes_item":
                return access(checksum, "bytes")
            elif c == "mixed_item":
                return access(checksum, "mixed")
            elif c == "keyorder":
                return keyorder(checksum)
    if deep:
        result = keyorder(checksum)
        if result is not None:
            _classify(checksum, "keyorder")
            return result
    return None


def find_url_info(checksum: Checksum, verbose: bool = False):
    """Get URL metadata via the FAIR server "access" API.
    Do not download the buffer."""
    checksum = Checksum(checksum)
    if not checksum:
        return None
    result = []
    if checksum in _direct_urls:
        result += _direct_urls[checksum]
    url_infos_buf = _download(
        checksum, "machine/access/", checksum_content=False, verbose=verbose
    )
    if url_infos_buf is not None:
        url_infos = json.loads(url_infos_buf.decode())
        result += url_infos
    if not result:
        return None
    return result


def _validate_params(
    type: str, version: str, date: str, format: str, compression: str
):  # pylint: disable=redefined-builtin
    if type not in (None, "deepcell", "deepfolder"):
        raise ValueError(type)
    if version is not None and not isinstance(version, (str, int)):
        raise TypeError
    if date is not None and not isinstance(date, str):
        raise TypeError
    if format is not None and not isinstance(format, str):
        raise TypeError
    if compression not in (None, "gzip", "bzip2", "none"):
        raise ValueError(compression)

    params = {}
    if type is not None:
        params["type"] = type
    if version is not None:
        params["version"] = str(version)
    if date is not None:
        params["date"] = date
    if format is not None:
        params["format"] = format
    if compression is not None:
        params["compression"] = compression
    return params


def find_distribution(  # pylint: disable=redefined-builtin
    dataset: str,
    *,
    type: str = None,
    version: str = None,
    date: str = None,
    format: str = None,
    compression: str = None
):
    """Find a specific distribution of a dataset, by version, date and/or format"""
    params = _validate_params(type, version, date, format, compression)
    params["dataset"] = dataset
    request = "/machine/find_distribution"
    urls = [urllib.parse.urljoin(server, request) for server in _servers]
    for url in urls:
        try:
            response = session.get(url, timeout=3, params=params)

            resp = response.status_code
            if int(resp / 100) == 3:
                raise RuntimeError(response.text)
            elif int(resp / 100) in (4, 5):
                continue
            else:
                distribution = response.json()
                keyorder_ = distribution.get("keyorder")
                if keyorder_ is not None:
                    _classify(keyorder_, "keyorder")
                return distribution
        except (ConnectionError, ReadTimeout):
            continue
    raise ConnectionError("Cannot contact any FAIR server")


def find_distribution_checksum(  # pylint: disable=redefined-builtin
    dataset: str,
    *,
    type: str | None = None,
    version: str | None = None,
    date: str | None = None,
    format: str | None = None,
    compression: str | None = None
):
    """Find a specific distribution of a dataset, by version, date and/or format.
    Return its checksum."""
    params = _validate_params(type, version, date, format, compression)
    params["dataset"] = dataset
    request = "/machine/find_checksum"
    urls = [urllib.parse.urljoin(server, request) for server in _servers]
    for url in urls:
        try:
            response = session.get(url, timeout=3, params=params)
            resp = response.status_code
            if int(resp / 100) == 3:
                raise RuntimeError(response.text)
            elif int(resp / 100) in (4, 5):
                continue
            else:
                checksum = Checksum(response.text.strip())
                return checksum
        except (ConnectionError, ReadTimeout):
            continue
    raise ConnectionError("Cannot contact any FAIR server")


__all__ = [
    "get_dataset",
    "find",
    "get_buffer",
    "access",
    "keyorder",
    "find_distribution",
    "find_distribution_checksum",
]


def __dir__():
    return sorted(__all__)
