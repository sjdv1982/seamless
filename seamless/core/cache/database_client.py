import re
import requests
import numpy as np
import json

from ..buffer_info import BufferInfo

session = requests.Session()

# TODO: make all set_X requests non-blocking, 
# by adding them into a queue and processing them 
#  in a different thread.
# (and have a set_X(key, value1) in the queue 
# superseded by a subsequent set_X(key, value2) request)

class DatabaseBase:
    active = False
    PROTOCOL = ("seamless", "database", "0.1")
    def _connect(self, host, port):
        self.host = host
        self.port = port
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "protocol",
        }
        response = session.get(url, data=json.dumps(request))
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
            "type": "has_buffer",
            "checksum": checksum.hex(),
        }
        response = session.get(url, data=json.dumps(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response.text == "1"

    def has_key(self, key):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "has_key",
            "key": key,
        }
        response = session.get(url, data=json.dumps(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response.text == "1"

    def delete_key(self, key):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "delete_key",
            "key": key,
        }
        response = session.put(url, data=json.dumps(request))
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
        if isinstance(request, bytes):
            rqbuf = request
        else:
            rqbuf = json.dumps(request)
        response = session.put(url, data=rqbuf)
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response

    def set_transformation_result(self, tf_checksum, checksum):
        request = {
            "type": "transformation",
            "checksum": tf_checksum.hex(),
            "value": checksum.hex(),
        }
        self.send_request(request)

    def sem2syn(self, semkey, syn_checksums):
        sem_checksum, celltype, subcelltype = semkey
        request = {
            "type": "semantic_to_syntactic",
            "checksum": sem_checksum.hex(),
            "celltype": celltype,
            "subcelltype": subcelltype,
            "value": list({cs.hex() for cs in syn_checksums}),
        }
        self.send_request(request)

    def set_buffer(self, checksum, buffer, persistent):
        '''
        # works, but only for string buffers...
        request = {
            "type": "buffer",
            "checksum": checksum.hex(),
            "value": buffer.decode(),
            "persistent": persistent,
        }
        rqbuf = json.dumps(request).encode()
        '''
        ps = chr(int(persistent)).encode()
        rqbuf = b'SEAMLESS_BUFFER' + checksum.hex().encode() + ps + buffer

        self.send_request(rqbuf)

    def set_buffer_info(self, checksum, buffer_info:BufferInfo):
        request = {
            "type": "buffer_info",
            "checksum": checksum.hex(),
            "value": buffer_info.as_dict(),
        }
        self.send_request(request)

    def set_compile_result(self, checksum, buffer):
        if not self.active:
            return
        if not self.store_compile_result:
            return
        request = {
            "type": "compilation",
            "checksum": checksum.hex(),
            "value": buffer,
        }
        self.send_request(request)

class DatabaseCache(DatabaseBase):
    def connect(self, *, host='localhost',port=5522):
        self._connect(host, port)

    def send_request(self, request):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        response = session.get(url, data=json.dumps(request))
        if response.status_code == 404:
            return None
        elif response.status_code >= 400:
            raise Exception(response.text)
        return response

    def get_transformation_result(self, checksum):
        request = {
            "type": "transformation",
            "checksum": checksum.hex(),
        }
        response = self.send_request(request)
        if response is not None:
            return bytes.fromhex(response.content.decode())

    def sem2syn(self, semkey):
        sem_checksum, celltype, subcelltype = semkey
        request = {
            "type": "semantic_to_syntactic",
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
            print("RESULT", result)
            verify_checksum = calculate_checksum(result)
            assert checksum == verify_checksum, "Database corruption!!! Checksum {}".format(checksum.hex())
            return result

    def get_buffer_info(self, checksum) -> BufferInfo:
        request = {
            "type": "buffer_info",
            "checksum": checksum.hex(),
        }
        response = self.send_request(request)
        if response is not None:
            return BufferInfo(checksum, response.json())

    def get_compile_result(self, checksum):
        request = {
            "type": "compilation",
            "checksum": checksum.hex(),
        }
        response = self.send_request(request)
        if response is not None:
            return bytes.fromhex(response.content.decode())


database_sink = DatabaseSink()
database_cache = DatabaseCache()

from ...calculate_checksum import calculate_checksum
