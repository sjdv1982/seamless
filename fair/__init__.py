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

def deepbuffer(checksum:str):
    if checksum is None:
        return None
    if isinstance(checksum, bytes):
        checksum = checksum.hex()
    request = "machine/deepbuffer/" + checksum
    urls = [urllib.parse.urljoin(server, request) for server in _servers]
    return download_buffer_sync(checksum, urls)