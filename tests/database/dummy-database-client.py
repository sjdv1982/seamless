import requests, json
import numpy as np
from seamless.mixed.io.serialization import serialize

url = "http://localhost:5522"


config = {
    "protocol": ("seamless", "database", "0.0.1"),
}

def main():
    checksum = "fa2fe6c9c0556871073be9a00d6d29bd3b9b6dd560587ee6e8c163755bf669d3"
    buffer = b'42\n'
    request = {
        "subtype": "buffer",
        "checksum": checksum,
        "value": np.frombuffer(buffer, dtype=np.uint8),
        "authoritative": False,
    }
    s = requests.Session()
    response = s.put(url, data=serialize(request))
    print(response.text)

    request = {
        "subtype": "buffer",
        "checksum": checksum,
    }
    response = s.get(url, data=serialize(request))
    print(response.text)

main()