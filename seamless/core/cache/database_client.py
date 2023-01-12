import requests
import json
import os
import sys

from ..buffer_info import BufferInfo

session = requests.Session()

# TODO: make all set_X requests non-blocking, 
# by adding them into a queue and processing them 
#  in a different thread.
# (and have a set_X(key, value1) in the queue 
# superseded by a subsequent set_X(key, value2) request)

class DatabaseBase:
    active = False
    PROTOCOLS = [("seamless", "database", "0.2"), ("seamless", "database", "0.1")]
    _loghandle = None

    def set_log(self, log):
        if isinstance(log, str):
            loghandle = open(str, "w")
        else:
            assert hasattr(log, "write")
            loghandle = log
        self._loghandle = loghandle

    def _log(self, type, checksum):
        if self._loghandle is None:
            return
        logstr = "{} {}\n".format(type, checksum)
        self._loghandle.write(logstr)

    def _get_host_port(self):
        env = os.environ
        host = env.get("SEAMLESS_DATABASE_IP")
        if host is None:
            raise ValueError("environment variable SEAMLESS_DATABASE_IP not defined")
        port = env.get("SEAMLESS_DATABASE_PORT")
        if port is None:
            raise ValueError("environment variable SEAMLESS_DATABASE_PORT not defined")
        try:
            port = int(port)
        except Exception:
            raise TypeError("environment variable SEAMLESS_DATABASE_PORT must be integer") from None
        return host, port

    def _connect(self, host, port, *, sink):
        self.host = host
        self.port = port
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "protocol",
        }
        try:
            response = session.get(url, data=json.dumps(request))
        except requests.ConnectionError:
            raise requests.ConnectionError("Cannot connect to Seamless database: host {}, port {}".format(self.host, self.port))

        try:
            protocol = response.json()
            assert protocol in [list(p) for p in self.PROTOCOLS]                
        except (AssertionError, ValueError, json.JSONDecodeError):
            raise Exception("Incorrect Seamless database protocol") from None


        if sink and float(protocol[-1]) > 0.1:
            request = {
                "type": "readonly",
            }
            try:
                response = session.get(url, data=json.dumps(request))
            except requests.ConnectionError:
                raise requests.ConnectionError("Cannot connect to Seamless database: host {}, port {}".format(self.host, self.port))
            try:
                readonly = response.json()
                assert readonly in (True, False)
            except (AssertionError, ValueError, json.JSONDecodeError):
                raise Exception("Incorrect Seamless database protocol") from None
            if readonly:
                return

        self.active = True

    def has_buffer(self, checksum):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "has_buffer",
            "checksum": parse_checksum(checksum),
        }
        response = session.get(url, data=json.dumps(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response.json() == True

    def delete_key(self, key_type, checksum):
        assert key_type in [
            "buffer",
            "buffer_info", 
            "transformation",
            "compilation",
            "buffer_independence", 
            "semantic_to_syntactic"
        ]
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "delete_key",
            "key_type": key_type,
            "checksum": parse_checksum(checksum)
        }
        response = session.put(url, data=json.dumps(request))
        if response.status_code != 200:
            raise Exception((response.status_code, response.text))
        return response.json() == True

class DatabaseSink(DatabaseBase):

    def connect(self, *,
      store_compile_result=True
    ):
        host, port = self._get_host_port()
        self.store_compile_result = store_compile_result
        self._connect(host, port, sink=True)

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
            "checksum": parse_checksum(tf_checksum),
            "value": parse_checksum(checksum),
        }
        self._log(request["type"], request["checksum"])
        self.send_request(request)

    def set_elision_result(self, elision_checksum, elision_result):        
        request = {
            "type": "elision",
            "checksum": parse_checksum(elision_checksum),
            "value": elision_result,
        }
        self._log(request["type"], request["checksum"])
        self.send_request(request)

    def sem2syn(self, semkey, syn_checksums):
        sem_checksum, celltype, subcelltype = semkey
        request = {
            "type": "semantic_to_syntactic",
            "checksum": parse_checksum(sem_checksum),
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
            "checksum": parse_checksum(checksum),
            "value": buffer.decode(),
            "persistent": persistent,
        }
        rqbuf = json.dumps(request).encode()
        '''
        ps = chr(int(persistent)).encode()
        rqbuf = b'SEAMLESS_BUFFER' + parse_checksum(checksum).encode() + ps + buffer
        self._log("buffer", parse_checksum(checksum))
        self.send_request(rqbuf)

    def set_buffer_info(self, checksum, buffer_info:BufferInfo):
        request = {
            "type": "buffer_info",
            "checksum": parse_checksum(checksum),
            "value": buffer_info.as_dict(),
        }
        self.send_request(request)

    def set_compile_result(self, checksum, compile_checksum):
        if not self.active:
            return
        if not self.store_compile_result:
            return
        request = {
            "type": "compilation",
            "checksum": parse_checksum(checksum),
            "value": parse_checksum(compile_checksum),
        }
        self._log(request["type"], request["checksum"])
        self.send_request(request)

class DatabaseCache(DatabaseBase):
    _filezones = None
    def set_filezones(self, filezones:list):
        if filezones is None:
            self._filezones = None
        else:
            if not isinstance(filezones, list):
                raise TypeError(filezones)
            self._filezones = [str(filezone) for filezone in filezones]
            
    def connect(self):
        host, port = self._get_host_port()
        self._connect(host, port, sink=False)

    def send_request(self, request):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        if isinstance(request, bytes):
            rqbuf = request
        else:
            rqbuf = json.dumps(request)
        response = session.get(url, data=rqbuf)
        if response.status_code == 404:
            return None
        elif response.status_code >= 400:
            raise Exception(response.text)
        return response

    def get_transformation_result(self, checksum):
        request = {
            "type": "transformation",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_request(request)
        if response is not None:
            result = bytes.fromhex(response.content.decode())
            self._log(request["type"], request["checksum"])
            return result

    def get_filename(self, checksum):
        request = {
            "type": "filename",
            "checksum": parse_checksum(checksum),
        }
        if self._filezones is not None:
            request["filezones"] = self._filezones
        response = self.send_request(request)
        if response is not None:
            return response.text

    def get_directory(self, checksum):
        request = {
            "type": "directory",
            "checksum": parse_checksum(checksum),
        }
        if self._filezones is not None:
            request["filezones"] = self._filezones
        response = self.send_request(request)
        if response is not None:
            return response.text

    def sem2syn(self, semkey):
        sem_checksum, celltype, subcelltype = semkey
        request = {
            "type": "semantic_to_syntactic",
            "checksum": parse_checksum(sem_checksum),
            "celltype": celltype,
            "subcelltype": subcelltype,
        }
        response = self.send_request(request)
        if response is not None:
            return [bytes.fromhex(cs.strip()) for cs in response.json()]

    def get_buffer(self, checksum):
        checksum = parse_checksum(checksum)
        request = {
            "type": "buffer",
            "checksum": checksum,
        }
        response = self.send_request(request)
        if response is not None:
            result = response.content
            verify_checksum = parse_checksum(calculate_checksum(result))
            assert checksum == verify_checksum, "Database corruption!!! Checksum {}".format(parse_checksum(checksum))
            self._log(request["type"], request["checksum"])
            return result

    def get_buffer_info(self, checksum) -> BufferInfo:
        request = {
            "type": "buffer_info",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_request(request)
        if response is not None:
            try:
                rj = response.json()
            except requests.exceptions.JSONDecodeError as exc:
                print(str(response.text())[:1000], file=sys.stderr)
                raise exc from None
            return BufferInfo(checksum, rj)

    def get_compile_result(self, checksum):
        request = {
            "type": "compilation",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_request(request)
        if response is not None:
            result = bytes.fromhex(response.content.decode())
            self._log(request["type"], request["checksum"])
            return result

    def get_elision_result(self, checksum):
        request = {
            "type": "elision",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_request(request)
        if response is not None:
            result = response.json()
            self._log(request["type"], request["checksum"])
            return result

database_sink = DatabaseSink()
database_cache = DatabaseCache()

from ...calculate_checksum import calculate_checksum
from ...util import parse_checksum