import requests
import numpy as np
import json

session = requests.Session()

class DatabaseBase:
    active = False
    PROTOCOL = ("seamless", "database", "0.0.2")
    def _connect(self, host, port):
        self.host = host
        self.port = port
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "protocol",
        }
        response = session.get(url, data=serialize(request))
        try:
            assert response.json() == list(self.PROTOCOL)
        except (AssertionError, ValueError, json.JSONDecodeError):
            raise Exception("Incorrect Seamless database protocol") from None
        self.active = True

    def has_buffer(self, checksum):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "has buffer",
            "checksum": checksum.hex(),
        }
        response = session.get(url, data=serialize(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response.text == "1"

    def has_key(self, key):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "has key",
            "key": key,
        }
        response = session.get(url, data=serialize(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response.text == "1"

    def delete_key(self, key):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "delete key",
            "key": key,
        }
        response = session.put(url, data=serialize(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response.text == "1"

class DatabaseSink(DatabaseBase):
    def connect(self, *, host='localhost',port=5522,
      store_compile_result=True
    ):
        self.store_compile_result = store_compile_result
        self._connect(host, port)

    def send_request(self, request):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        response = session.put(url, data=serialize(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response

    def set_transformation_result(self, tf_checksum, checksum):
        request = {
            "type": "transformation result",
            "checksum": tf_checksum.hex(),
            "value": checksum.hex(),
        }
        self.send_request(request)

    def sem2syn(self, semkey, syn_checksums):
        sem_checksum, celltype, subcelltype = semkey
        request = {
            "type": "semantic-to-syntactic",
            "checksum": sem_checksum.hex(),
            "celltype": celltype,
            "subcelltype": subcelltype,
            "value": list({cs.hex() for cs in syn_checksums}),
        }
        self.send_request(request)

    def set_buffer(self, checksum, buffer, persistent):
        request = {
            "type": "buffer",
            "checksum": checksum.hex(),
            "value": np.frombuffer(buffer, dtype=np.uint8),
            "persistent": persistent,
        }
        self.send_request(request)

    def set_buffer_length(self, checksum, length):
        request = {
            "type": "buffer length",
            "checksum": checksum.hex(),
            "value": length,
        }
        self.send_request(request)

    def set_compile_result(self, checksum, buffer):
        if not self.active:
            return
        if not self.store_compile_result:
            return
        request = {
            "type": "compile result",
            "checksum": checksum.hex(),
            "value": np.frombuffer(buffer, dtype=np.uint8),
        }
        self.send_request(request)

class DatabaseCache(DatabaseBase):
    def connect(self, *, host='localhost',port=5522):
        self._connect(host, port)

    def send_request(self, request):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        response = session.get(url, data=serialize(request))
        if response.status_code == 404:
            return None
        elif response.status_code >= 400:
            raise Exception(response.text)
        return response

    def get_transformation_result(self, checksum):
        request = {
            "type": "transformation result",
            "checksum": checksum.hex(),
        }
        response = self.send_request(request)
        if response is not None:
            return bytes.fromhex(response.content.decode())

    def sem2syn(self, semkey):
        sem_checksum, celltype, subcelltype = semkey
        request = {
            "type": "semantic-to-syntactic",
            "checksum": sem_checksum.hex(),
            "celltype": celltype,
            "subcelltype": subcelltype,
        }
        response = self.send_request(request)
        if response is not None:
            return [bytes.fromhex(cs.strip()) for cs in response.json()]

    def get_buffer(self, checksum):
        request = {
            "type": "buffer",
            "checksum": checksum.hex(),
        }
        response = self.send_request(request)
        if response is not None:
            result = response.content
            verify_checksum = get_hash(result)
            assert checksum == verify_checksum, "Database corruption!!! Checksum {}".format(checksum.hex())
            return result

    def get_buffer_length(self, checksum):
        request = {
            "type": "buffer length",
            "checksum": checksum.hex(),
        }
        response = self.send_request(request)
        if response is not None:
            return int(response.json())

    def get_compile_result(self, checksum):
        request = {
            "type": "compile result",
            "checksum": checksum.hex(),
        }
        response = self.send_request(request)
        if response is not None:
            return bytes.fromhex(response.content.decode())


database_sink = DatabaseSink()
database_cache = DatabaseCache()

from silk.mixed.io.serialization import serialize
from ...get_hash import get_hash
