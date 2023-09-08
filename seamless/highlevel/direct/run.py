"""Imperative transformations"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import inspect
import textwrap
import time
from types import LambdaType
import ast
import multiprocessing

from seamless.core.cache import CacheMissError

from ...calculate_checksum import calculate_checksum
from ...core.protocol.serialize import (
    serialize_sync as serialize,
    serialize as serialize_async,
)
from ...core.protocol.deserialize import (
    deserialize_sync as deserialize,
    deserialize as deserialize_async,
)
from ...core.protocol.get_buffer import get_buffer as _get_buffer
from ...core.lambdacode import lambdacode
from ...core.cache.transformation_cache import (
    transformation_cache,
    tf_get_buffer,
    incref_transformation,
    syntactic_is_semantic,
    DummyTransformer,
)
from ...core.cache.tempref import temprefmanager
from ...util import parse_checksum
from ... import run_transformation, run_transformation_async

_queued_transformations = []

_sem_code_cache = {}

TRANSFORMATION_STACK = []

import multiprocessing
from typing import Optional

_parent_process_queue:Optional[multiprocessing.JoinableQueue] = None
_parent_process_response_queue:Optional[multiprocessing.JoinableQueue] = None
_has_lock = True

_dummy_manager = None
def set_dummy_manager():
    global _dummy_manager
    if _dummy_manager is not None:
        return
    from seamless.core.manager import Manager
    _dummy_manager = Manager()

def _set_parent_process_queue(parent_process_queue):
    global _parent_process_queue
    _parent_process_queue = parent_process_queue


def _set_parent_process_response_queue(parent_process_response_queue):
    global _parent_process_response_queue
    _parent_process_response_queue = parent_process_response_queue


def getsource(func):
    from seamless.util import strip_decorators

    if isinstance(func, LambdaType) and func.__name__ == "<lambda>":
        code = lambdacode(func)
        if code is None:
            raise ValueError("Cannot extract source code from this lambda")
        return code
    else:
        code = inspect.getsource(func)
        code = textwrap.dedent(code)
        code = strip_decorators(code)
        return code


def cache_buffer(checksum, buf):
    from ...core.cache.buffer_cache import buffer_cache

    buffer_cache.cache_buffer(checksum, buf)


def get_buffer(checksum):
    result = _get_buffer(checksum, remote=True)
    if result is not None:
        return result
    return fingertip(checksum)
    
def fingertip(checksum):
    result = _get_buffer(checksum, remote=True)
    if result is not None:
        return result
    set_dummy_manager()
    async def fingertip_coro():
        return await _dummy_manager.cachemanager.fingertip(checksum)
    event_loop = asyncio.get_event_loop()
    if event_loop.is_running():
        with ThreadPoolExecutor() as tp:
            result = tp.submit(lambda: asyncio.run(fingertip_coro())).result()
    else:
        future = asyncio.ensure_future(_dummy_manager.cachemanager.fingertip(checksum))
        event_loop.run_until_complete(future)
        result = future.result()
    if result is None:
        raise CacheMissError(checksum.hex())
    return result
    


def _register_transformation_dict(
    transformation_checksum, transformation_buffer, transformation_dict
):
    # This is necessary to support transformation dicts that are not quite the same as their transformation buffers.
    # This happens in case of __meta__, __compilers__ or __languages__ fields in the dict
    # The transformation buffer has them stripped, so that transformations with different __meta__ get the same checksum.
    # See tf_get_buffer source code for details
    # In addition, the buffers in the checksum have now a Seamless refcount and will not be garbage collected.
    from ...core.cache.buffer_cache import buffer_cache

    result = None
    if (
        transformation_checksum
        not in transformation_cache.transformations_to_transformers
    ):
        transformation_cache.transformations_to_transformers[
            transformation_checksum
        ] = []
    if transformation_checksum not in transformation_cache.transformations:
        if transformation_checksum in transformation_cache.transformation_results:
            result_checksum, _ = transformation_cache.transformation_results[
                transformation_checksum
            ]
            buffer_cache.incref(result_checksum, False)
        incref_transformation(
            transformation_checksum, transformation_buffer, transformation_dict
        )
        result = DummyTransformer(transformation_checksum)
        transformation_cache.transformations_to_transformers[
            transformation_checksum
        ].append(result)
    transformation_cache.transformations[transformation_checksum] = transformation_dict
    return result


def run_transformation_dict(transformation_dict, fingertip):
    """Runs a transformation that is specified as a dict of checksums,
    such as returned by highlevel.Transformer.get_transformation_dict.
    """
    # TODO: add input schema and result schema validation...
    from ...core.cache.database_client import database
    from seamless.util import is_forked

    transformation_buffer = tf_get_buffer(transformation_dict)
    transformation = calculate_checksum(transformation_buffer)
    cache_buffer(transformation, transformation_buffer)
    increfed = _register_transformation_dict(
        transformation, transformation_buffer, transformation_dict
    )
    if is_forked():
        assert database.active
        result_checksum, prelim = transformation_cache._get_transformation_result(
            transformation
        )
        if result_checksum is not None and not prelim:
            metalike, syntactic_cache = None, []
        else:
            assert _parent_process_queue is not None
            metalike = {}
            for k in ("__compilers__", "__languages__", "__meta__"):
                if k in transformation_dict:
                    metalike[k] = transformation_dict[k]
            meta = metalike.get("__meta__")
            if meta is None:
                meta = {}
                metalike["__meta__"] = meta
            if meta.get("local") is None:
                # local (fat) by default
                meta["local"] = True
            syntactic_cache = []
            for k in transformation_dict:
                if k.startswith("__"):
                    continue
                celltype, subcelltype, sem_checksum = transformation_dict[k]
                if syntactic_is_semantic(celltype, subcelltype):
                    continue
                semkey = (bytes.fromhex(sem_checksum), celltype, subcelltype)
                syn_checksum = transformation_cache.semantic_to_syntactic_checksums[
                    semkey
                ][0]
                syn_buffer = get_buffer(syn_checksum)
                assert syn_buffer is not None
                syntactic_cache.append((celltype, subcelltype, syn_buffer))
    else:
        metalike, syntactic_cache = None, []
    
    result = None
    def result_callback(result2):
        nonlocal result
        result = result2
    
    _queued_transformations.append(
        (
            result_callback,
            transformation.hex(),
            transformation_dict,
            metalike,
            syntactic_cache,
            increfed,
            fingertip
        )
    )
    _wait()
    return result

async def run_transformation_dict_async(transformation_dict):
    """Runs a transformation that is specified as a dict of checksums,
    such as returned by highlevel.Transformer.get_transformation_dict"""
    # TODO: add input schema and result schema validation...
    from seamless.util import is_forked

    assert not is_forked()
    transformation_buffer = tf_get_buffer(transformation_dict)
    transformation = calculate_checksum(transformation_buffer)
    cache_buffer(transformation, transformation_buffer)
    increfed = _register_transformation_dict(
        transformation, transformation_buffer, transformation_dict
    )
    try:
        result_checksum = await run_transformation_async(transformation, fingertip=False)
    finally:
        # For some reason, the logic here is different than for the sync version (see _wait())
        if (
            increfed
            and increfed
            in transformation_cache.transformations_to_transformers.get(
                transformation, []
            )
        ):
            transformation_cache.decref_transformation(transformation_dict, increfed)
        temprefmanager.purge_group("imperative")
    
    return result_checksum

def prepare_transformation_dict(transformation_dict):
    """Prepares transformation dict for submission.
    
Takes an "unprepared" transformation dict where some checksums have been replaced by
(uncached) buffers or values, and replaces them back with proper (semantic) checksums.
Checksum instances replaced with their hex values.
Replaced buffers or values are properly registered and cached 
(including their syntactic <=> semantic conversion).
"""

    from .. import Checksum
    from ...core.cache.buffer_remote import write_buffer as remote_write_buffer
    from ...core.cache.database_client import database
    from .Transformation import Transformation
    
    non_checksum_items = ("__output__", "__language__", "__meta__", "__env__")    

    argnames = list(transformation_dict.keys())
    for argname in argnames:
        if argname in non_checksum_items:
            continue
        arg = transformation_dict[argname]
        celltype = None
        celltype, _, value = arg

        original_value = value
        if isinstance(value, Checksum):
            pass
        elif value is None:
            value = Checksum(value)
        elif isinstance(value, Transformation):
            assert value.status == "Status: OK", value.status  # must have been checked before
            checksum = value.checksum
            assert checksum is not None  # can't be true if status is OK
            value = Checksum(checksum)
        else:
            if isinstance(value, bytes):
                buf = value
            else:
                buf = serialize(value, celltype)
            checksum = calculate_checksum(buf, hex=False)
            assert isinstance(checksum, bytes)
            cache_buffer(checksum, buf)
            value = Checksum(checksum)

        if argname == "code":
            assert isinstance(value, Checksum), type(value)
            code = original_value if not isinstance(original_value, Checksum) else None
            code_checksum = value.bytes()
            semantic_code_checksum2 = _get_semantic(code, code_checksum)
            if semantic_code_checksum2 is None:
                raise CacheMissError(code_checksum.hex())
            assert isinstance(semantic_code_checksum2, bytes)
            semantic_code_checksum = semantic_code_checksum2.hex()
            try:
                try:
                    semcode = _sem_code_cache[semantic_code_checksum2]
                except KeyError:
                    try:
                        semcode = fingertip(semantic_code_checksum2)
                        _sem_code_cache[semantic_code_checksum2] = semcode
                    except CacheMissError as exc:
                        raise exc from None
                cache_buffer(semantic_code_checksum2, semcode)
            except KeyError:
                semcode = get_buffer(semantic_code_checksum2)
                if semcode is None:
                    raise CacheMissError(semantic_code_checksum2) from None
            remote_write_buffer(semantic_code_checksum2, semcode)
            if code is not None:
                codebuf = serialize(code, "python")
                remote_write_buffer(code_checksum, codebuf)
            semkey = (semantic_code_checksum2, "python", "transformer")
            database.set_sem2syn(semkey, [code_checksum])
            value = Checksum(semantic_code_checksum)

        assert isinstance(value, Checksum), (argname, value)
        value = value.value

        arg = arg[0], arg[1], value
        transformation_dict[argname] = arg

    return transformation_dict


def _direct_transformer_to_transformation_dict(
    codebuf,
    meta,
    celltypes,
    modules,
    arguments,
    env
):
    from seamless.highlevel import Base, Cell, Module
    from seamless.highlevel.DeepCell import DeepCellBase
    from .Transformation import Transformation
    from .. import Checksum

    result_celltype = celltypes["result"]
    result_hash_pattern = None
    if result_celltype == "deepcell":
        result_celltype = "mixed"
        result_hash_pattern = {"*": "#"}
    elif result_celltype == "folder":
        result_celltype = "mixed"
        result_hash_pattern = {"*": "##"}
    elif result_celltype == "structured":
        result_celltype = "mixed"
    
    outputpin = ("result", result_celltype, None)
    if result_hash_pattern is not None:
        outputpin += (result_hash_pattern,)

    transformation_dict = {
        "__output__": outputpin,
        "__language__": "python",
    }

    if env is not None:
        envbuf = serialize(env, "plain")
        checksum = calculate_checksum(envbuf)
        cache_buffer(checksum, envbuf)
        transformation_dict["__env__"] = checksum.hex()
    
    if meta:
        transformation_dict["__meta__"] = meta
    
    tf_pins = {}

    arguments2 = arguments.copy()
    for pinname, module_code in modules.items():
        arguments2[pinname] = module_code
        pin = {
            "celltype": "plain",
            "subcelltype": "module"
        }
        tf_pins[pinname] = pin

    for pinname,celltype in celltypes.items():
        if celltype is None or celltype == "default":
            if pinname.endswith("_SCHEMA"):
                celltype = "plain"
            else:
                celltype = "mixed"
        if celltype == "silk":
            celltype = "mixed"
        if celltype == "checksum":
            celltype = "plain"

        if celltype in ("cson", "yaml", "python"):
            raise NotImplementedError(pinname)
                
        if celltype == "module":
            pin = {
                "celltype": "plain",
                "subcelltype": "module"
            }
        elif celltype in ("folder", "deepfolder", "deepcell"):
            if celltype == "deepcell":
                pin = {
                    "celltype": "mixed",
                    "hash_pattern": {"*": "#"},
                }
            elif celltype == "deepfolder":
                pin = {
                    "celltype": "mixed",
                    "hash_pattern": {"*": "##"},
                    "filesystem": {
                        "mode": "directory",
                        "optional": False
                    },
                }
            elif celltype == "folder":
                pin = {
                    "celltype": "mixed",
                    "hash_pattern": {"*": "##"},
                    "filesystem": {
                        "mode": "directory",
                        "optional": True
                    },
                }
        else:
            pin = {"celltype": celltype}
        tf_pins[pinname] = pin

    tf_pins["code"] = {"celltype": "python", "subcelltype": "transformer"}
    arguments2["code"] = codebuf

    for pinname, pin in tf_pins.items():
        if pinname == "result":
            continue
        value = arguments2[pinname]

        if isinstance(value, Base):
            assert isinstance(value, (Cell, Module, DeepCellBase))
            checksum = value.checksum
            if checksum is None:
                raise ValueError(f"Argument {pinname} (Cell {value}) has no checksum available")
            v = Checksum(checksum)
        elif isinstance(value, Transformation):
            v = value
        else:
            v = value

        transformation_dict[pinname] = (pin["celltype"], pin.get("subcelltype"), v)
    assert "code" in transformation_dict
    assert transformation_dict["code"][2] is not None, transformation_dict["code"]
    return transformation_dict

def _get_semantic(code, code_checksum):
    from ...util import ast_dump
    
    code_checksum = parse_checksum(code_checksum, as_bytes=True)
    synkey = (code_checksum, "python", "transformer")
    semantic_code_checksum = transformation_cache.syntactic_to_semantic_checksums.get(synkey)
    if semantic_code_checksum is not None:
        return semantic_code_checksum
    
    if code is None:
        code = get_buffer(code_checksum)
    if code is None:
        raise CacheMissError(code_checksum.hex())
    tree = ast.parse(code, filename="<None>")
    semcode = ast_dump(tree).encode()
    semantic_code_checksum = calculate_checksum(semcode, hex=False)
    _sem_code_cache[semantic_code_checksum] = semcode
    transformation_cache.syntactic_to_semantic_checksums[synkey] = semantic_code_checksum
    key = (semantic_code_checksum, "python", "transformer")
    cache = transformation_cache.semantic_to_syntactic_checksums
    if key not in cache:
        cache[key] = []
    if code_checksum not in cache[key]:
        cache[key].append(code_checksum)
    return semantic_code_checksum

def _get_node_transformation_dependencies(node):
    from .Transformation import Transformation
    deps = {}
    temp = node.get("TEMP", {}).get("input_auth", {})
    for pinname, value in temp.items():
        value = temp[pinname]
        if isinstance(value, Transformation):
            deps[pinname] = value
    return deps

def _node_to_transformation_dict(node):
    # builds transformation dict from highlevel.Transformer node
    # - node must be unbound (inputs come from .TEMP and .checksum items).
    # - Transformation dependencies inside .TEMP can be present
    # - The result transformation dict cannot be submitted directly,
    #    it must still be prepared.

    from seamless.highlevel import Base, Cell, Module
    from seamless.highlevel.DeepCell import DeepCellBase
    from .Transformation import Transformation
    from .. import Checksum

    language = node["language"]
    if language == "bash":
        raise NotImplementedError  # substitute bash code checksum, see rprod bash_transformation

    result_name = node["RESULT"]
    if node["language"] != "python":
        assert result_name == "result"
    assert result_name not in node["pins"] #should have been checked by highlevel
    result_celltype = node.get("result_celltype", "structured")
    result_hash_pattern = None
    if result_celltype == "deepcell":
        result_celltype = "mixed"
        result_hash_pattern = {"*": "#"}
    elif result_celltype == "folder":
        result_celltype = "mixed"
        result_hash_pattern = {"*": "##"}
    elif result_celltype == "structured":
        result_celltype = "mixed"
    
    outputpin = (result_name, result_celltype, None)
    if result_hash_pattern is not None:
        outputpin += (result_hash_pattern,)

    transformation_dict = {
        "__output__": outputpin,
        "__language__": language,
    }
    env = node.get("environment")
    if env is not None:
        envbuf = serialize(env, "plain")
        checksum = calculate_checksum(envbuf)
        cache_buffer(checksum, envbuf)
        transformation_dict["__env__"] = checksum.hex()
    
    meta = node.get("meta")
    if meta:
        transformation_dict["__meta__"] = meta
    node_pins = deepcopy(node["pins"])
    
    tf_pins = {}
    for pinname,pin in list(node_pins.items()):
        celltype = pin.get("celltype")
        if celltype is None or celltype == "default":
            if pinname.endswith("_SCHEMA"):
                celltype = "plain"
            else:
                celltype = "mixed"
        if celltype == "silk":
            celltype = "mixed"
        if celltype == "checksum":
            celltype = "plain"

        if celltype in ("cson", "yaml", "python"):
            raise NotImplementedError(pinname)
        
        pin.pop("subcelltype", None) # just to make sure...
        if celltype == "module":
            pin = {
                "celltype": "plain",
                "subcelltype": "module"
            }
        elif celltype in ("folder", "deepfolder", "deepcell"):
            if celltype == "deepcell":
                pin = {
                    "celltype": "mixed",
                    "hash_pattern": {"*": "#"},
                }
            elif celltype == "deepfolder":
                pin = {
                    "celltype": "mixed",
                    "hash_pattern": {"*": "##"},
                    "filesystem": {
                        "mode": "directory",
                        "optional": False
                    },
                }
            elif celltype == "folder":
                pin = {
                    "celltype": "mixed",
                    "hash_pattern": {"*": "##"},
                    "filesystem": {
                        "mode": "directory",
                        "optional": True
                    },
                }
        else:
            pin["celltype"] = celltype
        tf_pins[pinname] = pin
    tf_pins["code"] = {"celltype": "python", "subcelltype": "transformer"}


    temp = node.get("TEMP", {}).get("input_auth", {}).copy()
    if "code" in node.get("TEMP", {}):
        temp["code"] = node["TEMP"]["code"]
    elif "code" in node.get("checksum", {}):
        temp["code"] = Checksum(node["checksum"]["code"])

    for pinname, pin in tf_pins.items():
        v = None
        if pinname in temp:
            value = temp[pinname]
            if isinstance(value, Base):
                assert isinstance(value, (Cell, Module, DeepCellBase))
                checksum = value.checksum
                if checksum is None:
                    raise ValueError(f"Argument {pinname} (Cell {value}) has no checksum available")
                v = Checksum(checksum)
            elif isinstance(value, Transformation):
                v = value
            else:
                v = value

        transformation_dict[pinname] = (pin["celltype"], pin.get("subcelltype"), v)
    assert "code" in transformation_dict
    assert transformation_dict["code"][2] is not None, transformation_dict["code"]
    return transformation_dict




def _wait():
    from seamless.util import is_forked
    global _queued_transformations
    global _has_lock
    from seamless import CacheMissError
    if not _queued_transformations:
        return None
    results = []
    queued_transformations = _queued_transformations.copy()
    _queued_transformations.clear()
    had_lock = _has_lock
    # NOTE: for future optimization, one could run transformations in batch mode.
    #   one batch for the parent process queue, and one batch for local run_transformation
    if is_forked() and _has_lock:
        _parent_process_queue.put((5, "release lock"))
        _has_lock = False
    try:
        for (
            result_callback,
            transformation,
            transformation_dict,
            metalike,
            syntactic_cache,
            increfed,
            fingertip
        ) in queued_transformations:
            if is_forked():
                #print(f"Delegate to parent: {transformation}, fingertip = {fingertip}, stack = {TRANSFORMATION_STACK}")
                assert transformation not in TRANSFORMATION_STACK
                _parent_process_queue.put(
                    (7, (transformation, metalike, syntactic_cache, fingertip))
                )
        for (
            result_callback,
            transformation,
            transformation_dict,
            metalike,
            syntactic_cache,
            increfed,
            fingertip
        ) in queued_transformations:
            try:
                tf_checksum = bytes.fromhex(transformation)
                if is_forked():
                    while 1:
                        ###tf_checksum2, result_checksum, logs = _parent_process_response_queue.get(timeout=15) ###
                        tf_checksum2, result_checksum, logs = _parent_process_response_queue.get()
                        if tf_checksum2 != tf_checksum.hex():
                            _parent_process_response_queue.put((tf_checksum2, result_checksum, logs))
                            time.sleep(0.1)
                            continue
                        _parent_process_response_queue.task_done()
                        break
                    if result_checksum is not None:
                        assert isinstance(result_checksum, bytes)
                        transformation_cache.register_known_transformation(tf_checksum, result_checksum)
                    transformation_cache.transformation_logs[tf_checksum] = logs
                else:
                    running_event_loop = asyncio.get_event_loop().is_running()
                    result_checksum = run_transformation(transformation, fingertip=fingertip, new_event_loop=running_event_loop)  # new_event_loop used to be True...
                    if result_checksum is not None:
                        assert isinstance(result_checksum, bytes)                        

            finally:
                # For some reason, the logic here is different than for the async version
                # (see run_transformation_dict_async)
                temprefmanager.purge_group("imperative")
                if (
                    increfed
                    and bytes.fromhex(transformation)
                    in transformation_cache.transformations
                ):
                    transformation_cache.decref_transformation(
                        transformation_dict, increfed
                    )
                temprefmanager.purge_group("imperative")

            results.append((result_callback, result_checksum))
    finally:
        if is_forked() and had_lock and not _has_lock:
            _parent_process_queue.put((6, "acquire lock"))
            _has_lock = True
    for result_callback, result_checksum in results:
        result_callback(result_checksum)


def _cleanup():
    """is registered atexit by seamless.core, because it must run first"""
    for (
        _,
        transformation,
        transformation_dict,
        _,
        _,
        increfed,
        _,
    ) in _queued_transformations:
        # For some reason, the logic here is different than for the async version
        # (see run_transformation_dict_async)
        if (
            increfed
            and bytes.fromhex(transformation) in transformation_cache.transformations
        ):
            transformation_cache.decref_transformation(transformation_dict, increfed)

