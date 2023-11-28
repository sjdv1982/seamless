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

    def connect(self, host, port):
        global Expression
        from ..manager.expression import Expression
        self.host = host
        self.port = port
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "protocol",
        }   
        ntrials=5
        for trial in range(ntrials):     
            try:
                with session.get(url, data=json.dumps(request)) as response:
                    if response.status_code != 200:
                        raise Exception(response.text)

                    try:
                        protocol = response.json()
                        assert protocol in [list(p) for p in self.PROTOCOLS]                
                    except (AssertionError, ValueError, json.JSONDecodeError):
                        raise Exception("Incorrect Seamless database protocol") from None
                    
            except requests.ConnectionError:
                if trial < ntrials - 1:
                    continue
                raise requests.ConnectionError("Cannot connect to Seamless database: host {}, port {}".format(self.host, self.port))


        self.active = True

    def send_put_request(self, request, *, raise_exception=True):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        if isinstance(request, bytes):
            rqbuf = request
        else:
            rqbuf = json.dumps(request)
        with session.put(url, data=rqbuf) as response:
            if raise_exception and response.status_code != 200:
                raise Exception((response.status_code, response.text))
            return response.status_code, response.text

    def set_transformation_result(self, tf_checksum, checksum):   
        request = {
            "type": "transformation",
            "checksum": parse_checksum(tf_checksum),
            "value": parse_checksum(checksum),
        }
        self._log("SET", request["type"], request["checksum"])
        self.send_put_request(request)

    def set_elision_result(self, elision_checksum, elision_result_checksum):
        request = {
            "type": "elision",
            "checksum": parse_checksum(elision_checksum),
            "value": parse_checksum(elision_result_checksum),
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

    def set_buffer_length(self, checksum, buffer_length:int):
        buffer_info = BufferInfo(checksum)
        buffer_info.length = buffer_length
        return self.set_buffer_info(checksum, buffer_info)

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
        assert result is not None
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
            "value": json.dumps(metadata, sort_keys=True, indent=2) + "\n",
        }
        self._log("SET", request["type"], request["type"])
        self.send_put_request(request)

     
    def set_structured_cell_join(self, checksum, join_checksum):
        request = {
            "type": "structured_cell_join",
            "checksum": parse_checksum(join_checksum),
            "value": parse_checksum(checksum)
        }
        self._log("SET", request["type"], request["type"])
        self.send_put_request(request)

    def contest(self, transformation_checksum:bytes, result_checksum:bytes):
        """Contests a previously calculated transformation result"""
        transformation_checksum = parse_checksum(transformation_checksum, as_bytes=False)
        assert transformation_checksum is not None
        result_checksum = parse_checksum(result_checksum, as_bytes=False)
        assert result_checksum is not None
        request = {
            "type": "contest",
            "checksum": transformation_checksum,
            "result": result_checksum,
        }
        status_code, response_text = self.send_put_request(request, raise_exception=False)
        return status_code, response_text

    def send_get_request(self, request):
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        if isinstance(request, bytes):
            rqbuf = request
        else:
            rqbuf = json.dumps(request)
        with session.get(url, data=rqbuf) as response:
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
            result = parse_checksum(response.content.decode(), as_bytes=True)
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
            result = parse_checksum(response.content.decode(), as_bytes=True)
            self._log("GET", request["type"], request["checksum"])
            return result

    def get_elision_result(self, checksum):
        request = {
            "type": "elision",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_get_request(request)
        if response is not None:
            result = parse_checksum(response.content.decode(), as_bytes=True)
            self._log("GET", request["type"], request["checksum"])
            return result

    def get_rev_expression(self, checksum):
        request = {
            "type": "rev_expression",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_get_request(request)
        if response is not None:
            self._log("GET", request["type"], request["checksum"])
            try:
                rj = response.json()
            except requests.exceptions.JSONDecodeError as exc:
                print(str(response.text())[:1000], file=sys.stderr)
                raise exc from None
            if not rj:
                return None
            return rj

    def get_rev_join(self, checksum):
        request = {
            "type": "rev_join",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_get_request(request)
        if response is not None:
            self._log("GET", request["type"], request["checksum"])
            try:
                rj = response.json()
            except requests.exceptions.JSONDecodeError as exc:
                print(str(response.text())[:1000], file=sys.stderr)
                raise exc from None
            if not rj:
                return None
            return rj

    def get_rev_transformations(self, checksum):
        request = {
            "type": "rev_transformations",
            "checksum": parse_checksum(checksum),
        }
        response = self.send_get_request(request)
        if response is not None:
            self._log("GET", request["type"], request["checksum"])
            try:
                rtf = response.json()
            except requests.exceptions.JSONDecodeError as exc:
                print(str(response.text())[:1000], file=sys.stderr)
                raise exc from None
            if not rtf:
                return None
            return rtf

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
            result = parse_checksum(response.content.decode(), as_bytes=True)
            self._log("GET", request["type"], request["checksum"])
            return result

    def get_metadata(self, tf_checksum) -> dict:
        request = {
            "type": "metadata",
            "checksum": parse_checksum(tf_checksum)
        }
        self._log("GET", request["type"], request["type"])
        response = self.send_get_request(request)
        if response is not None:
            try:
                rj = response.json()
            except requests.exceptions.JSONDecodeError as exc:
                print(str(response.text())[:1000], file=sys.stderr)
                raise exc from None
            return rj

    def get_structured_cell_join(self, join_dict: dict):
        checksum = calculate_dict_checksum(join_dict)
        request = {
            "type": "structured_cell_join",
            "checksum": parse_checksum(checksum)
        }
        response = self.send_get_request(request)
        if response is not None:
            result = parse_checksum(response.content.decode(), as_bytes=True)
            self._log("GET", request["type"], request["checksum"])
            return result


database = Database()

from ...util import parse_checksum
from ...calculate_checksum import calculate_dict_checksum