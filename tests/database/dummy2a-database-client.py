import requests, json


url = "http://localhost:5522"


config = {
    "protocol": ("seamless", "database", "0.1"),
}

def main():
    checksum = "fa2fe6c9c0556871073be9a00d6d29bd3b9b6dd560587ee6e8c163755bf669d3"
    buffer = b'42\n'
    """
    request = {
        "type": "buffer",
        "checksum": checksum,
        "value": buffer.decode(),
        "persistent": True,
    }
    rqbuf = json.dumps(request)
    """
    ps = chr(1).encode()
    rqbuf = b'SEAMLESS_BUFFER' + checksum.encode() + ps + buffer

    s = requests.Session()
    response = s.put(url, data=rqbuf)

    print(response.text)

    request = {
        "type": "buffer",
        "checksum": checksum,
    }
    response = s.get(url, data=json.dumps(request))
    print(response.text)

main()