import json
import urllib.parse
from seamless.download_buffer import download_buffer_sync, session
from requests.exceptions import ConnectionError, ReadTimeout

_servers = [
    "http://localhost:61918",
    "https://fair.rpbs.univ-paris-diderot.fr"
]

def get_servers():
    return _servers.copy()

def add_server(url):
    _servers.append(url)

_classification = {
    "deepbuffer": set(),
    "bytes_item": set(),
    "mixed_item": set(),
    "keyorder": set(),
}  
def _classify(checksum:str, classification: str):
    if classification not in ("deepbuffer" , "bytes_item" , "mixed_item", "keyorder"):
        raise ValueError(classification)
    if isinstance(checksum, bytes):
        checksum = checksum.hex()
    if len(checksum) != 64:
        raise ValueError(checksum)
    try:
        bytes.fromhex(checksum)
    except Exception:
        raise ValueError(checksum)
    _classification[classification].add(checksum)

def _download(checksum:str, template, *, checksum_content:bool):
    if checksum is None:
        return None
    if isinstance(checksum, bytes):
        checksum = checksum.hex()
    if len(checksum) != 64:
        raise ValueError(checksum)
    try:
        bytes.fromhex(checksum)
    except Exception:
        raise ValueError(checksum)
    request = template + checksum
    urls = [urllib.parse.urljoin(server, request) for server in _servers]
    checksum2 = checksum if checksum_content else None
    return download_buffer_sync(checksum2, urls)

def get_dataset(dataset:str):
    request = "/machine/dataset/{}".format(dataset)
    urls = [urllib.parse.urljoin(server, request) for server in _servers]
    datasetbuffer = download_buffer_sync(None, urls)
    if datasetbuffer is not None:
        return json.loads(datasetbuffer.decode())

def find(checksum:str):
    if checksum is None:
        return None
    if isinstance(checksum, bytes):
        checksum = checksum.hex()
    if len(checksum) != 64:
        raise ValueError(checksum)
    try:
        bytes.fromhex(checksum)
    except Exception:
        raise ValueError(checksum)
    request = "/machine/find/" + checksum
    urls = [urllib.parse.urljoin(server, request) for server in _servers]
    for url in urls:
        try:
            response = session.get(url, timeout=3)
            if int(response.status_code/100) in (4,5):
                #raise Exception(response.text + ": " + checksum)        
                continue
            else:
                return response.json()
        except (ConnectionError, ReadTimeout):
            continue
    raise ConnectionError("Cannot contact any FAIR server")

def deepbuffer(checksum:str):
    return _download(checksum, "machine/deepbuffer/", checksum_content=True)

def keyorder(checksum:str):
    return _download(checksum, "machine/keyorder/", checksum_content=False)

def access(checksum:str, celltype):
    url_infos_buf = _download(checksum, "machine/access/", checksum_content=False)
    if url_infos_buf is None:
        return None
    url_infos = json.loads(url_infos_buf.decode())
    return download_buffer_sync(checksum, url_infos, celltype)

def get_buffer(checksum:str, deep=False):
    if checksum is None:
        return None
    if isinstance(checksum, bytes):
        checksum = checksum.hex()    
    if len(checksum) != 64:
        raise ValueError(checksum)
    try:
        bytes.fromhex(checksum)
    except Exception:
        raise ValueError(checksum)
    for c in _classification:
        if checksum in _classification[c]:
            if c == "deepbuffer":
                return deepbuffer(checksum)
            elif c == "bytes_item":
                return access(checksum, "bytes")
            elif c == "mixed_item":
                return access(checksum, "mixed")
            elif c == "keyorder":
                return keyorder(checksum)
    if deep:
        result = deepbuffer(checksum)
        if result is not None:
            _classify(checksum, "deepbuffer")
            return result
        result = keyorder(checksum)
        if result is not None:
            _classify(checksum, "keyorder")
            return result
    return None

def _validate_params(type:str, version:str, date:str, format:str, compression:str):
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
        params["version"] = version
    if date is not None:
        params["date"] = date
    if format is not None:
        params["format"] = format
    if compression is not None:
        params["compression"] = compression
    return params

def find_distribution(dataset:str, *, type:str=None, version:str=None, date:str=None, format:str=None, compression:str=None):
    params = _validate_params(type, version, date, format, compression)
    params["dataset"] = dataset
    request = "/machine/find_distribution"
    urls = [urllib.parse.urljoin(server, request) for server in _servers]
    for url in urls:
        try:
            response = session.get(url, timeout=3, params=params)            
            resp = response.status_code
            if int(resp/100) == 3:
                raise Exception(response.text) 
            elif int(resp/100) in (4,5):
                continue       
            else:
                distribution = response.json()
                _classify(distribution["checksum"], "deepbuffer")
                keyorder = distribution.get("keyorder")
                if keyorder is not None:
                    _classify(keyorder, "keyorder")
                return distribution
        except (ConnectionError, ReadTimeout):
            continue
    raise ConnectionError("Cannot contact any FAIR server")        

def find_checksum(dataset:str, *, type:str=None, version:str=None, date:str=None, format:str=None, compression:str=None):
    params = _validate_params(type, version, date, format, compression)
    params["dataset"] = dataset
    request = "/machine/find_checksum"
    urls = [urllib.parse.urljoin(server, request) for server in _servers]
    for url in urls:
        try:
            response = session.get(url, timeout=3, params=params)
            resp = response.status_code
            if int(resp/100) == 3:
                raise Exception(response.text) 
            elif int(resp/100) in (4,5):
                continue       
            else:
                checksum = response.text.strip()
                if len(checksum) != 64:
                    raise ValueError(checksum)
                bytes.fromhex(checksum)
                _classify(checksum, "deepbuffer")
                return checksum
        except (ConnectionError, ReadTimeout):
            continue
    raise ConnectionError("Cannot contact any FAIR server")        

__all__ = ["get_dataset", "find", "get_buffer", "deepbuffer", "access", "keyorder", "find_distribution", "find_checksum"]