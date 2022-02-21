import json
import urllib.parse

from seamless.download_buffer import download_buffer_sync 

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
def classify(checksum:str, classification: str):
    if classification not in ("deepbuffer" , "bytes_item" , "mixed_item", "keyorder"):
        raise ValueError(classification)
    if isinstance(checksum, bytes):
        checksum = checksum.hex()
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
    try:
        bytes.fromhex(checksum)
    except Exception:
        raise ValueError(checksum)
    request = template + checksum
    urls = [urllib.parse.urljoin(server, request) for server in _servers]
    checksum2 = checksum if checksum_content else None
    return download_buffer_sync(checksum2, urls)

def deepbuffer(checksum:str):
    return _download(checksum, "machine/deepbuffer/", checksum_content=True)

def download(checksum:str, celltype):
    url_infos_buf = _download(checksum, "machine/download/", checksum_content=False)
    if url_infos_buf is None:
        return None
    url_infos = json.loads(url_infos_buf.decode())
    return download_buffer_sync(checksum, url_infos, celltype)

def get_buffer(checksum:str):
    if checksum is None:
        return None
    if isinstance(checksum, bytes):
        checksum = checksum.hex()    
    try:
        bytes.fromhex(checksum)
    except Exception:
        raise ValueError(checksum)
    for c in _classification:
        if checksum in _classification[c]:
            if c == "deepbuffer":
                return deepbuffer(checksum)
            elif c == "bytes_item":
                return download(checksum, "bytes")
            elif c == "mixed_item":
                return download(checksum, "mixed")
        