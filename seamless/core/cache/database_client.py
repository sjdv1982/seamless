import requests
import json
import os
import sys

from ..buffer_info import BufferInfo

session = requests.Session()

# TODO (if proven to be a bottleneck): 
#  make all set_X requests non-blocking, 
# by adding them into a queue and processing them 
#  in a different thread.
# (and have a set_X(key, value1) in the queue 
# superseded by a subsequent set_X(key, value2) request)

global Expression

class Database:
    active = False
    PROTOCOLS = [("seamless", "database", "0.3")]
    _loghandle = None

    def set_log(self, log):
        if isinstance(log, str):
            loghandle = open(str, "w")
        else:
            assert hasattr(log, "write")
            loghandle = log
        self._loghandle = loghandle

    def _log(self, getset, type, checksum):
        if self._loghandle is None:
            return
        logstr = "{} {} {}\n".format(getset, type, checksum)
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

    def _connect(self, host, port):
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

        if response.status_code != 200:
            raise Exception(response.text)

        try:
            protocol = response.json()
            assert protocol in [list(p) for p in self.PROTOCOLS]                
        except (AssertionError, ValueError, json.JSONDecodeError):
            raise Exception("Incorrect Seamless database protocol") from None

        self.active = True

    def connect(self):
        global Expression
        from ..manager.expression import Expression
        host, port = self._get_host_port()
        self._connect(host, port)

    def delete_key(self, key_type, checksum):
        assert key_type in [
            "buffer_info",
            "compilation",
            "transformation",
            "elision",
            "metadata",
            "expression",
            "structured_cell_join",
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

    def delete_syntactic_to_semantic(self, *, semantic, syntactic, celltype, subcelltype):
        raise NotImplementedError

    def send_put_request(self, request):
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
        self._log("SET", request["type"], request["checksum"])
        self.send_put_request(request)

    def set_elision_result(self, elision_checksum, elision_result):        
        request = {
            "type": "elision",
            "checksum": parse_checksum(elision_checksum),
            "value": elision_result,
        }
        self._log("SET", request["type"], request["checksum"])
        self.send_put_request(request)

    def set_sem2syn(self, semkey, syn_checksums):
        sem_checksum, celltype, subcelltype = semkey
        request = {
            "type": "semantic_to_syntactic",
            "checksum": parse_checksum(sem_checksum),
            "celltype": celltype,
            "subcelltype": subcelltype,
            "value": list({cs.hex() for cs in syn_checksums}),
        }
        self.send_put_request(request)

    def set_buffer_info(self, checksum, buffer_info:BufferInfo):
        request = {
            "type": "buffer_info",
            "checksum": parse_checksum(checksum),
            "value": buffer_info.as_dict(),
        }
        self.send_put_request(request)

    def set_compile_result(self, checksum, compile_checksum):
        if not self.active:
            return
        request = {
            "type": "compilation",
            "checksum": parse_checksum(checksum),
            "value": parse_checksum(compile_checksum),
        }
        self._log("SET", request["type"], request["checksum"])
        self.send_put_request(request)
            
    def set_expression(self, expression: "Expression", result):
        request = {
            "type": "expression",
            "checksum": parse_checksum(expression.checksum),
            "celltype": expression.celltype,
            "path": expression.path,        
            "value": parse_checksum(result),
            "target_celltype": expression.target_celltype,
        }
        if expression.hash_pattern is not None:
            request["hash_pattern"] = expression.hash_pattern
        if expression.target_hash_pattern is not None:
            request["target_hash_pattern"] = expression.target_hash_pattern
        self._log("SET", request["type"], str(expression))
        self.send_put_request(request)

    def set_metadata(self, tf_checksum,  metadata:dict):
        tf_checksum = parse_checksum(tf_checksum) 
        if not self.active:
            return
        request = {
            "type": "metadata",
            "checksum": parse_checksum(tf_checksum),
            "value": json.dumps(metadata),
        }
        self._log("SET", request["type"], request["type"])
        self.send_put_request(request)

    def send_get_request(self, request):
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
        response = self.send_get_request(request)
        if response is not None:
            result = bytes.fromhex(response.content.decode())
            self._log("GET", request["type"], request["checksum"])
            return result


    def get_sem2syn(self, semkey):
        sem_checksum, celltype, subcelltype = semkey
        request = {
            "type": "semantic_to_syntactic",
            "checksum": parse_checksum(sem_checksum),
            "celltype": celltype,
            "subcelltype": subcelltype,
        }
        response = self.send_get_request(request)
        if response is not None:
            return [bytes.fromhex(cs.strip()) for cs in response.json()]

    def get_buffer_info(self, checksum) -> BufferInfo:
        request = {
            "type": "buffer_info",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_get_request(request)
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
        response = self.send_get_request(request)
        if response is not None:
            result = bytes.fromhex(response.content.decode())
            self._log("GET", request["type"], request["checksum"])
            return result

    def get_elision_result(self, checksum):
        request = {
            "type": "elision",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_get_request(request)
        if response is not None:
            result = bytes.fromhex(response.content.decode())
            self._log("GET", request["type"], request["checksum"])
            return result

    def get_expression(self, expression: "Expression"):
        request = {
            "type": "expression",
            "checksum": parse_checksum(expression.checksum),
            "celltype": expression.celltype,
            "path": expression.path,        
            "target_celltype": expression.target_celltype,
        }
        if expression.hash_pattern is not None:
            request["hash_pattern"] = expression.hash_pattern
        if expression.target_hash_pattern is not None:
            request["target_hash_pattern"] = expression.target_hash_pattern
        response = self.send_get_request(request)
        if response is not None:
            result = bytes.fromhex(response.content.decode())
            self._log("GET", request["type"], request["checksum"])
            return result

    def get_metadata(self, tf_checksum) -> dict:
        request = {
            "type": "metadata",
            "checksum": parse_checksum(tf_checksum)
        }
        self._log("SET", request["type"], request["type"])
        response = self.send_get_request(request)
        if response is not None:
            try:
                rj = response.json()
            except requests.exceptions.JSONDecodeError as exc:
                print(str(response.text())[:1000], file=sys.stderr)
                raise exc from None
            return rj

class Dummy:
    _connected = False    
    
    @property
    def active(self):
        if not self._connected:
            return False
        return database.active
    
    def connect(self):
        if not self._connected:
            print(DeprecationWarning("""'database_sink' and 'database_cache' are deprecated.
                                     Use 'database' instead"""))
            database.connect()
            self._connected = True

    def __getattr__(self, attr):
        return getattr(database, attr)

database = Database()
database_sink = Dummy()
database_cache = Dummy()

from ...util import parse_checksum