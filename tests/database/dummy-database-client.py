import requests, json
import numpy as np
from seamless.mixed.io.serialization import serialize

url = "http://localhost:5522"


config = {
    "protocol": ("seamless", "database", "0.0.1"),
}

def main():
    s = requests.Session()
    request = {
        "type": "protocol",
    }
    response = s.get(url, data=serialize(request))
    try:
        assert response.json() == ["seamless", "database", "0.0.2"]
    except (AssertionError, ValueError, json.JSONDecodeError):
        raise Exception("Incorrect Seamless database protocol") from None
    checksum = "fa2fe6c9c0556871073be9a00d6d29bd3b9b6dd560587ee6e8c163755bf669d3"
    buffer = b'42\n'
    request = {
        "type": "buffer",
        "checksum": checksum,
        "value": np.frombuffer(buffer, dtype=np.uint8),
        "persistent": False,
    }
    response = s.put(url, data=serialize(request))
    print(response.text)

    request = {
        "type": "has buffer",
        "checksum": checksum,
    }
    response = s.get(url, data=serialize(request))
    print(response.text, response.text == "1")

    request = {
        "type": "buffer",
        "checksum": checksum,
    }
    response = s.get(url, data=serialize(request))
    print(response.text)

main()