"""Client for Seamless database"""

import threading
import json
import sys
import weakref
import asyncio
import atexit

import requests
import aiohttp

from seamless import Checksum, Buffer
from seamless.util import unchecksum
from seamless.checksum import Expression
from seamless.checksum.buffer_info import BufferInfo

session = requests.Session()
sessions_async = weakref.WeakKeyDictionary()


class Database:
    """Client for Seamless database"""

    active = False
    PROTOCOLS = [("seamless", "database", "0.3")]
    host = None
    port = None
    _loghandle = None

    def set_log(self, log):
        """Define log. log can be a filename or File-like object"""
        if isinstance(log, str):
            loghandle = open(str, "w")
        else:
            assert hasattr(log, "write")
            loghandle = log
        self._loghandle = loghandle

    def _log(self, getset, type, checksum):  # pylint: disable=redefined-builtin
        if self._loghandle is None:
            return
        logstr = "{} {} {}\n".format(getset, type, checksum)
        self._loghandle.write(logstr)

    def connect(self, host: str, port: int) -> None:
        """Connect to a Seamless database at http://host:port.
        HTTP protocol is assumed."""

        self.host = str(host)
        self.port = int(port)
        url = "http://" + self.host + ":" + str(self.port)
        request = {
            "type": "protocol",
        }
        ntrials = 5
        for trial in range(ntrials):
            try:
                with session.get(url, data=json.dumps(request)) as response:
                    if response.status_code != 200:
                        raise RuntimeError(response.text)

                    try:
                        protocol = response.json()
                        assert protocol in [list(p) for p in self.PROTOCOLS]
                    except (AssertionError, ValueError, json.JSONDecodeError):
                        raise RuntimeError(
                            "Incorrect Seamless database protocol"
                        ) from None

            except requests.ConnectionError:
                if trial < ntrials - 1:
                    continue
                raise requests.ConnectionError(
                    "Cannot connect to Seamless database: host {}, port {}".format(
                        self.host, self.port
                    )
                ) from None

        self.active = True

    def send_put_request(self, request: dict | bytes, *, raise_exception=True):
        """Send a PUT request, which can be a parameter dict or raw data"""
        if not self.active:
            return
        url = "http://" + self.host + ":" + str(self.port)
        if isinstance(request, bytes):
            rqbuf = request
        else:
            rqbuf = json.dumps(request)
        with session.put(url, data=rqbuf) as response:
            if raise_exception and response.status_code != 200:
                raise RuntimeError((response.status_code, response.text))
            return response.status_code, response.text

    def set_transformation_result(self, tf_checksum: Checksum, checksum: Checksum):
        """Set <checksum> as the transformation result of <tf_checksum>"""
        request = {
            "type": "transformation",
            "checksum": Checksum(tf_checksum).value,
            "value": Checksum(checksum).value,
        }
        self._log("SET", request["type"], request["checksum"])
        self.send_put_request(request)

    def set_elision_result(
        self, elision_checksum: Checksum, elision_result_checksum: Checksum
    ):
        """Set <elision_result_checksum> as the result of <elision_checksum>"""
        request = {
            "type": "elision",
            "checksum": Checksum(elision_checksum).value,
            "value": Checksum(elision_result_checksum).value,
        }
        self._log("SET", request["type"], request["checksum"])
        self.send_put_request(request)

    def set_sem2syn(
        self, semkey: tuple[str, str, str | None], syn_checksums: list[Checksum]
    ):
        """Set <syn_checksums> as the origin checksums of a syntactic-to-semantic operation
        <semkey> is a tuple of semantic checksum, celltype and subcelltype."""
        sem_checksum, celltype, subcelltype = semkey
        request = {
            "type": "semantic_to_syntactic",
            "checksum": Checksum(sem_checksum).value,
            "celltype": celltype,
            "subcelltype": subcelltype,
            "value": list({Checksum(cs).hex() for cs in syn_checksums}),
        }
        self.send_put_request(request)

    def set_buffer_info(self, checksum: Checksum, buffer_info: BufferInfo):
        """Set BufferInfo for a checksum"""
        request = {
            "type": "buffer_info",
            "checksum": Checksum(checksum).value,
            "value": BufferInfo(checksum, buffer_info).as_dict(),
        }
        self.send_put_request(request)

    def set_buffer_length(self, checksum: Checksum, buffer_length: int):
        """Specify the buffer length of a checksum"""
        checksum = Checksum(checksum)
        buffer_info = BufferInfo(checksum)
        buffer_info.length = buffer_length
        return self.set_buffer_info(checksum, buffer_info)

    def set_compile_result(self, checksum: Checksum, compile_checksum: Checksum):
        """Set the compilation result of a checksum.
        DISABLED."""
        return  ###
        """
        if not self.active:
            return
        request = {
            "type": "compilation",
            "checksum": Checksum(checksum).value,
            "value": Checksum(compile_checksum).value,
        }
        self._log("SET", request["type"], request["checksum"])
        self.send_put_request(request)
        """

    def set_expression(self, expression: Expression, result: Checksum):
        """Set the result checksum of an expression"""
        assert result
        request = {
            "type": "expression",
            "checksum": Checksum(expression.checksum).value,
            "celltype": expression.celltype,
            "path": expression.path,
            "value": Checksum(result).value,
            "target_celltype": expression.target_celltype,
        }
        if expression.hash_pattern is not None:
            request["hash_pattern"] = expression.hash_pattern
        if expression.target_hash_pattern is not None:
            request["target_hash_pattern"] = expression.target_hash_pattern
        self._log("SET", request["type"], str(expression))
        self.send_put_request(request)

    def set_metadata(self, tf_checksum: Checksum, metadata: dict):
        """Set transformation metadata.
        tf_checksum: transformation checksum"""
        tf_checksum = Checksum(tf_checksum).value
        if not self.active:
            return
        request = {
            "type": "metadata",
            "checksum": Checksum(tf_checksum).value,
            "value": json.dumps(metadata, sort_keys=True, indent=2) + "\n",
        }
        self._log("SET", request["type"], request["type"])
        self.send_put_request(request)

    def set_structured_cell_join(
        self, *, result_checksum: Checksum, join_checksum: Checksum
    ):
        """Set the result of a structured cell join.
        join_checksum is the checksum of the join dict (deep checksum)"""
        request = {
            "type": "structured_cell_join",
            "checksum": Checksum(join_checksum).value,
            "value": Checksum(result_checksum).value,
        }
        self._log("SET", request["type"], request["type"])
        self.send_put_request(request)

    def contest(self, transformation_checksum: Checksum, result_checksum: Checksum):
        """Contests a previously calculated transformation result"""
        transformation_checksum = Checksum(transformation_checksum)
        assert transformation_checksum
        result_checksum = Checksum(result_checksum)
        assert result_checksum
        request = {
            "type": "contest",
            "checksum": transformation_checksum,
            "result": result_checksum,
        }
        status_code, response_text = self.send_put_request(
            request, raise_exception=False
        )
        return status_code, response_text

    def send_get_request(self, request: dict | bytes):
        """Send a GET request, which can be a parameter dict or raw data"""
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
                raise RuntimeError(response.text)
            return response

    async def send_get_request_async(self, request: dict | bytes):
        """Send a GET request, which can be a parameter dict or raw data"""
        if not self.active:
            return

        thread = threading.current_thread()
        session_async = sessions_async.get(thread)
        if session_async is not None:
            try:
                loop = asyncio.get_running_loop()
                if loop != session_async._loop:
                    session_async = None
            except RuntimeError:  # no event loop running:
                pass
        if session_async is None:
            session_async = aiohttp.ClientSession()
            sessions_async[thread] = session_async

        url = "http://" + self.host + ":" + str(self.port)
        if isinstance(request, bytes):
            rqbuf = request
        else:
            rqbuf = json.dumps(request)
        async with session_async.get(url, data=rqbuf) as response:
            if response.status == 404:
                return None
            elif response.status >= 400:
                text = await response.text.read()
                raise RuntimeError(text)
            return await response.content.read()

    def get_transformation_result(self, tf_checksum: Checksum) -> Checksum | None:
        """Get transformation result"""
        request = {
            "type": "transformation",
            "checksum": Checksum(tf_checksum).value,
        }
        response = self.send_get_request(request)
        if response is not None:
            result = Checksum(response.content.decode())
            self._log("GET", request["type"], request["checksum"])
            return result

    async def get_transformation_result_async(
        self, tf_checksum: Checksum
    ) -> Checksum | None:
        """Get transformation result"""
        request = {
            "type": "transformation",
            "checksum": Checksum(tf_checksum).value,
        }
        content = await self.send_get_request_async(request)
        if content is not None:
            result = Checksum(content.decode())
            self._log("GET", request["type"], request["checksum"])
            return result

    def get_sem2syn(self, semkey: tuple[str, str, str | None]) -> list[Checksum]:
        """Get the origin checksums of a syntactic-to-semantic operation
        <semkey> is a tuple of semantic checksum, celltype and subcelltype."""

        sem_checksum, celltype, subcelltype = semkey
        request = {
            "type": "semantic_to_syntactic",
            "checksum": Checksum(sem_checksum).value,
            "celltype": celltype,
            "subcelltype": subcelltype,
        }
        response = self.send_get_request(request)
        if response is not None:
            return [bytes.fromhex(cs.strip()) for cs in response.json()]

    def get_buffer_info(self, checksum: Checksum) -> BufferInfo:
        """Get BufferInfo for a checksum"""
        request = {
            "type": "buffer_info",
            "checksum": Checksum(checksum).value,
        }
        response = self.send_get_request(request)
        if response is not None:
            try:
                rj = response.json()
            except requests.exceptions.JSONDecodeError as exc:
                print(str(response.text())[:1000], file=sys.stderr)
                raise exc from None
            return BufferInfo(checksum, rj)

    def get_compile_result(self, checksum: Checksum):
        """Get the compilation result of a checksum.
        DISABLED."""
        return  ###
        """
        request = {
            "type": "compilation",
            "checksum": Checksum(checksum).value,
        }
        response = self.send_get_request(request)
        if response is not None:
            result = Checksum(response.content.decode())
            self._log("GET", request["type"], request["checksum"])
            return result
        """

    def get_elision_result(self, elision_checksum: Checksum):
        """Get the elision result of <elision_checksum>"""
        request = {
            "type": "elision",
            "checksum": Checksum(elision_checksum).value,
        }
        response = self.send_get_request(request)
        if response is not None:
            result = Checksum(response.content.decode())
            self._log("GET", request["type"], request["checksum"])
            return result

    def get_rev_expression(self, result_checksum: Checksum) -> list[Checksum]:
        """Get the checksums of expressions that evaluate to <result_checksum>"""
        request = {
            "type": "rev_expression",
            "checksum": Checksum(result_checksum).value,
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

    def get_rev_join(self, result_checksum: Checksum) -> list[Checksum]:
        """Get the checksums of structured cell joins that evaluate to <result_checksum>"""
        request = {
            "type": "rev_join",
            "checksum": Checksum(result_checksum).value,
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

    def get_rev_transformations(self, result_checksum):
        """Get the checksums of transformations that evaluate to <result_checksum>"""
        request = {
            "type": "rev_transformations",
            "checksum": Checksum(result_checksum).value,
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

    def get_expression(self, expression: Expression) -> Checksum:
        """Get the result of an expression"""
        request = {
            "type": "expression",
            "checksum": Checksum(expression.checksum).value,
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
            result = Checksum(response.content.decode())
            self._log("GET", request["type"], request["checksum"])
            return result

    def get_metadata(self, tf_checksum: Checksum) -> dict:
        """Get transformation metadata.
        tf_checksum: transformation checksum"""
        request = {"type": "metadata", "checksum": Checksum(tf_checksum).value}
        self._log("GET", request["type"], request["type"])
        response = self.send_get_request(request)
        if response is not None:
            try:
                rj = response.json()
            except requests.exceptions.JSONDecodeError as exc:
                print(str(response.text())[:1000], file=sys.stderr)
                raise exc from None
            return rj

    def get_structured_cell_join(self, join_dict: dict) -> Checksum | None:
        """Get the result of a structured cell join"""
        join_dict2 = unchecksum(join_dict)
        checksum = Buffer(join_dict2, "plain").get_checksum().value
        request = {"type": "structured_cell_join", "checksum": checksum}
        response = self.send_get_request(request)
        if response is not None:
            result = Checksum(response.content.decode())
            self._log("GET", request["type"], request["checksum"])
            return result


database = Database()


def _close_async_sessions():
    for session_async in sessions_async.values():
        asyncio.ensure_future(session_async.close())


atexit.register(_close_async_sessions)
