"""Imperative transformations"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import ast
import time
import multiprocessing
from typing import Optional

from seamless import CacheMissError, Checksum

from seamless.checksum.get_buffer import (
    get_buffer as _get_buffer,
    get_buffer_async as _get_buffer_async,
)
from seamless.checksum.buffer_cache import buffer_cache
from seamless.checksum import buffer_remote
from seamless.checksum.database_client import database
from seamless.checksum.calculate_checksum import calculate_checksum
from seamless.checksum.cached_compile import exec_code
from seamless.checksum.serialize import serialize_sync
from seamless.util import parse_checksum
from seamless.util.source import ast_dump
from seamless.util.transformation import tf_get_buffer, extract_dunder
from seamless.direct import transformer, Transformation

from ...core.cache.transformation_cache import (
    transformation_cache,
    incref_transformation,
    syntactic_is_semantic,
    DummyTransformer,
)
from seamless.workflow.tempref import temprefmanager
from seamless.direct import run_transformation, run_transformation_async

_queued_transformations = []

_sem_code_cache = {}

TRANSFORMATION_STACK = []

_parent_process_queue: Optional[multiprocessing.JoinableQueue] = None
_parent_process_response_queue: Optional[multiprocessing.JoinableQueue] = None
_has_lock = True

_dummy_manager = None


def get_dummy_manager():
    if _dummy_manager is None:
        set_dummy_manager()
    return _dummy_manager


def set_dummy_manager():
    global _dummy_manager
    if _dummy_manager is not None:
        return
    from seamless.workflow.core.manager import Manager

    _dummy_manager = Manager()


def set_parent_process_queue(parent_process_queue):
    global _parent_process_queue
    _parent_process_queue = parent_process_queue


def set_parent_process_response_queue(parent_process_response_queue):
    global _parent_process_response_queue
    _parent_process_response_queue = parent_process_response_queue


def cache_buffer(checksum, buf):

    checksum = parse_checksum(checksum, as_bytes=True)
    buffer_cache.cache_buffer(checksum, buf)
    buffer_remote.write_buffer(checksum, buf)


def get_buffer(checksum):
    checksum = parse_checksum(checksum, as_bytes=True)
    result = _get_buffer(checksum, remote=True)
    if result is not None:
        return result
    return fingertip(checksum)


def fingertip(checksum, dunder=None):

    checksum = parse_checksum(checksum, as_bytes=True)
    result = _get_buffer(checksum, remote=True)
    if result is not None:
        return result
    set_dummy_manager()

    async def fingertip_coro():
        return await _dummy_manager.cachemanager.fingertip(checksum, dunder=dunder)

    event_loop = asyncio.get_event_loop()
    if event_loop.is_running():
        with ThreadPoolExecutor() as tp:
            result = tp.submit(lambda: asyncio.run(fingertip_coro())).result()
    else:
        future = asyncio.ensure_future(
            _dummy_manager.cachemanager.fingertip(checksum, dunder=dunder)
        )
        event_loop.run_until_complete(future)
        result = future.result()
    if result is None:
        raise CacheMissError(checksum.hex())
    return result


async def fingertip_async(checksum, dunder=None):

    checksum = parse_checksum(checksum, as_bytes=True)
    result = await _get_buffer_async(checksum, remote=True)
    if result is not None:
        return result
    set_dummy_manager()

    result = await _dummy_manager.cachemanager.fingertip(checksum, dunder=dunder)
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
            buffer_cache.incref(result_checksum, persistent=False)
        incref_transformation(
            transformation_checksum, transformation_buffer, transformation_dict
        )
        result = DummyTransformer(transformation_checksum)
        transformation_cache.transformations_to_transformers[
            transformation_checksum
        ].append(result)
    transformation_cache.transformations[transformation_checksum] = transformation_dict
    return result


def register_transformation_dict(transformation_dict, dry_run=False):
    transformation_buffer = tf_get_buffer(transformation_dict)
    transformation = calculate_checksum(transformation_buffer)
    if not dry_run:
        cache_buffer(transformation, transformation_buffer)
        increfed = _register_transformation_dict(
            transformation, transformation_buffer, transformation_dict
        )
    else:
        increfed = False
    return increfed, transformation


def run_transformation_dict(
    transformation_dict, *, fingertip, scratch=False, in_process=False
):
    """Runs a transformation that is specified as a dict of checksums,
    such as returned by highlevel.Transformer.get_transformation_dict.
    """
    # TODO: add input schema and result schema validation...
    from seamless.util.is_forked import is_forked

    increfed, transformation = register_transformation_dict(transformation_dict)
    tf_dunder = extract_dunder(transformation_dict)
    if is_forked():
        assert not in_process
        assert database.active
        result_checksum, prelim = transformation_cache._get_transformation_result(
            transformation
        )
        result_checksum = Checksum(result_checksum)
        if result_checksum and not prelim:
            tf_dunder, syntactic_cache = None, []
        else:
            assert _parent_process_queue is not None
            syntactic_cache = []
            for k in transformation_dict:
                if k.startswith("__"):
                    continue
                celltype, subcelltype, sem_checksum = transformation_dict[k]
                if syntactic_is_semantic(celltype, subcelltype):
                    continue
                semkey = (Checksum(sem_checksum), celltype, subcelltype)
                syn_checksums = transformation_cache.semantic_to_syntactic_checksums[
                    semkey
                ]
                syn_checksum = syn_checksums[0]
                syn_buffer = get_buffer(syn_checksum)
                assert syn_buffer is not None
                syntactic_cache.append((celltype, subcelltype, syn_buffer))
                database.set_sem2syn(semkey, syn_checksums)

                if tf_dunder is None:
                    tf_dunder = {}
                meta = tf_dunder.get("__meta__")
                if meta is None:
                    meta = {}
                    tf_dunder["__meta__"] = meta
                if meta.get("local") is None:
                    # local (fat) by default
                    meta["local"] = True

    else:
        syntactic_cache = []

    if in_process:
        return run_transformation_dict_in_process(
            transformation_dict, transformation, tf_dunder, scratch
        )
    result = None

    def result_callback(result2):
        nonlocal result
        result = result2

    _queued_transformations.append(
        (
            result_callback,
            transformation.hex(),
            transformation_dict,
            tf_dunder,
            syntactic_cache,
            increfed,
            fingertip,
            scratch,
        )
    )
    _wait()
    return result


async def run_transformation_dict_async(
    transformation_dict, *, fingertip, scratch=False
):
    """Runs a transformation that is specified as a dict of checksums,
    such as returned by highlevel.Transformer.get_transformation_dict"""
    # TODO: add input schema and result schema validation...
    from seamless.util.is_forked import is_forked

    assert not is_forked()
    transformation_buffer = tf_get_buffer(transformation_dict)
    tf_dunder = extract_dunder(transformation_dict)
    transformation = calculate_checksum(transformation_buffer)
    result_checksum = await run_transformation_async(
        transformation,
        scratch=scratch,
        fingertip=fingertip,
        tf_dunder=tf_dunder,
        cache_only=True,
    )
    result_checksum = Checksum(result_checksum)
    if result_checksum:
        ###buffer_cache.decref(result_checksum) #TODO: look into this
        return result_checksum

    if "__code_checksum__" in transformation_dict:
        semkey = (transformation_dict["code"][2], "python", "transformer")
        database.set_sem2syn(semkey, [transformation_dict["__code_checksum__"]])

    cache_buffer(transformation, transformation_buffer)
    increfed = _register_transformation_dict(
        transformation, transformation_buffer, transformation_dict
    )
    try:
        result_checksum = await run_transformation_async(
            transformation, scratch=scratch, fingertip=fingertip, tf_dunder=tf_dunder
        )
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


def run_transformation_dict_in_process(
    transformation_dict, tf_checksum, tf_dunder, scratch
):
    from seamless.workflow.core.transformation import (
        execution_metadata0,
        get_global_info,
        get_transformation_inputs_output,
        build_transformation_namespace_sync,
        build_all_modules,
    )
    from seamless.compiler import (
        compilers as default_compilers,
        languages as default_languages,
    )
    from seamless.workflow.core.injector import transformer_injector as injector

    result_checksum = database.get_transformation_result(tf_checksum)
    result_checksum = Checksum(result_checksum)
    if result_checksum:
        return result_checksum

    get_global_info()
    execution_metadata = deepcopy(execution_metadata0)
    if "Executor" not in execution_metadata:
        execution_metadata["Executor"] = "seamless-in-process"

    transformation = {}
    transformation.update(transformation_dict)
    transformation.update(tf_dunder)

    if transformation.get("__language__") == "bash":
        raise NotImplementedError

    env_checksum0 = transformation.get("__env__")
    if env_checksum0 is not None:
        raise NotImplementedError

    semantic_cache = transformation_cache.build_semantic_cache(transformation)

    io = get_transformation_inputs_output(transformation)
    inputs, output_name, output_celltype, output_subcelltype, output_hash_pattern = io
    tf_namespace = build_transformation_namespace_sync(
        transformation, semantic_cache, "transformer-in-process"
    )
    code, namespace, modules_to_build, deep_structures_to_unpack = tf_namespace

    if deep_structures_to_unpack:
        raise NotImplementedError

    if output_hash_pattern is not None:
        raise NotImplementedError

    module_workspace = {}
    compilers = transformation.get("__compilers__", default_compilers)
    languages = transformation.get("__languages__", default_languages)

    build_all_modules(
        modules_to_build,
        module_workspace,
        compilers=compilers,
        languages=languages,
        module_debug_mounts=None,
    )
    assert code is not None

    namespace["transformer"] = transformer
    namespace.pop(output_name, None)
    with injector.active_workspace(module_workspace, namespace):
        exec_code(
            code,
            "transformer-in-process",
            namespace,
            inputs,
            output_name,
            with_ipython_kernel=False,
        )
        try:
            result = namespace[output_name]
        except KeyError:
            msg = "Output variable name '%s' undefined" % output_name
            raise RuntimeError(msg) from None

    if result is None:
        raise RuntimeError("Result is empty")

    result_buffer = serialize_sync(result, output_celltype)
    result_checksum = calculate_checksum(result_buffer)

    database.set_transformation_result(tf_checksum, result_checksum)
    if not scratch:
        buffer_cache.guarantee_buffer_info(
            result_checksum, output_celltype, sync_to_remote=True
        )
        buffer_cache.cache_buffer(result_checksum, result_buffer)
        buffer_remote.write_buffer(result_checksum, result_buffer)

    return result_checksum


def prepare_code(semantic_code_checksum, codebuf, code_checksum):
    if codebuf is not None:
        assert isinstance(codebuf, bytes)
    semantic_code_checksum = Checksum(semantic_code_checksum).bytes()
    code_checksum = Checksum(code_checksum).bytes()
    assert semantic_code_checksum
    try:
        try:
            semcode = _sem_code_cache[semantic_code_checksum]
        except KeyError:
            try:
                semcode = fingertip(semantic_code_checksum)
                _sem_code_cache[semantic_code_checksum] = semcode
            except CacheMissError as exc:
                raise exc from None
        cache_buffer(semantic_code_checksum, semcode)
    except KeyError:
        semcode = get_buffer(semantic_code_checksum)
        if semcode is None:
            raise CacheMissError(semantic_code_checksum) from None
    cache_buffer(code_checksum, codebuf)
    value = Checksum(semantic_code_checksum)
    return value


def prepare_transformation_pin_value(value, celltype):
    if isinstance(value, Checksum):
        pass
    elif value is None:
        value = Checksum(value)
    elif isinstance(value, Transformation):
        assert (
            value.status == "Status: OK"
        ), value.status  # must have been checked before
        checksum = value.checksum
        checksum = Checksum(checksum)
        assert checksum  # can't be true if status is OK
        value = checksum
    else:
        if isinstance(value, bytes):
            buf = value
        else:
            buf = serialize_sync(value, celltype)
        checksum = calculate_checksum(buf, hex=False)
        assert isinstance(checksum, bytes)
        cache_buffer(checksum, buf)
        value = Checksum(checksum)
    return value


def prepare_transformation_dict(transformation_dict):
    """Prepares transformation dict for submission.

    Takes an "unprepared" transformation dict where some checksums have been replaced by
    (uncached) buffers or values, and replaces them back with proper (semantic) checksums.
    Checksum instances replaced with their hex values.
    Replaced buffers or values are properly registered and cached
    (including their syntactic <=> semantic conversion).
    """

    non_checksum_items = (
        "__output__",
        "__language__",
        "__meta__",
        "__env__",
        "__format__",
    )

    argnames = list(transformation_dict.keys())
    for argname in argnames:
        if argname in non_checksum_items:
            continue
        arg = transformation_dict[argname]
        celltype = None
        celltype, _, value = arg

        original_value = value
        value = prepare_transformation_pin_value(value, celltype)

        if argname == "code":
            assert isinstance(value, Checksum), type(value)
            code = original_value if not isinstance(original_value, Checksum) else None
            code_checksum = value.bytes()
            semantic_code_checksum = _get_semantic(code, code_checksum)
            semantic_code_checksum = Checksum(semantic_code_checksum)
            if not semantic_code_checksum:
                raise CacheMissError(code_checksum.hex())
            codebuf = None
            if code is not None:
                codebuf = serialize_sync(code, "python")
            value = prepare_code(semantic_code_checksum, codebuf, code_checksum)
            transformation_dict["__code_checksum__"] = code_checksum

        assert isinstance(value, Checksum), (argname, value)
        value = value.value

        arg = arg[0], arg[1], value
        transformation_dict[argname] = arg


def direct_transformer_to_transformation_dict(
    codebuf, meta, celltypes, modules, arguments, env
):
    from seamless.workflow.highlevel import Base, Cell, Module
    from seamless.workflow.highlevel.DeepCell import DeepCellBase

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
        envbuf = serialize_sync(env, "plain")
        checksum = calculate_checksum(envbuf)
        cache_buffer(checksum, envbuf)
        transformation_dict["__env__"] = checksum.hex()

    if meta:
        transformation_dict["__meta__"] = meta.copy()

    tf_pins = {}

    arguments2 = arguments.copy()
    for pinname, module_code in modules.items():
        arguments2[pinname] = module_code
        pin = {"celltype": "plain", "subcelltype": "module"}
        tf_pins[pinname] = pin

    for pinname, celltype in celltypes.items():
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
            pin = {"celltype": "plain", "subcelltype": "module"}
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
                    "filesystem": {"mode": "directory", "optional": False},
                }
            elif celltype == "folder":
                pin = {
                    "celltype": "mixed",
                    "hash_pattern": {"*": "##"},
                    "filesystem": {"mode": "directory", "optional": True},
                }
        else:
            pin = {"celltype": celltype}
        tf_pins[pinname] = pin

    tf_pins["code"] = {"celltype": "python", "subcelltype": "transformer"}
    arguments2["code"] = codebuf

    FORMAT = {}

    for pinname, pin in tf_pins.items():
        if pinname == "result":
            continue
        value = arguments2[pinname]

        if isinstance(value, Base):
            assert isinstance(value, (Cell, Module, DeepCellBase))
            checksum = value.checksum
            checksum = Checksum(checksum)
            if not checksum:
                raise ValueError(
                    f"Argument {pinname} (Cell {value}) has no checksum available"
                )
            v = checksum
        elif isinstance(value, Transformation):
            v = value
        else:
            v = value

        transformation_dict[pinname] = (pin["celltype"], pin.get("subcelltype"), v)
        hash_pattern = pin.get("hash_pattern")
        filesystem = pin.get("filesystem")
        if filesystem is not None or hash_pattern is not None:
            FORMAT[pinname] = {}
        if filesystem is not None:
            FORMAT[pinname]["filesystem"] = deepcopy(filesystem)
        if hash_pattern is not None:
            FORMAT[pinname]["hash_pattern"] = deepcopy(hash_pattern)

    assert "code" in transformation_dict
    assert transformation_dict["code"][2] is not None, transformation_dict["code"]
    if len(FORMAT):
        transformation_dict["__format__"] = FORMAT
    return transformation_dict


def _get_semantic(code, code_checksum):
    code_checksum = parse_checksum(code_checksum, as_bytes=True)
    synkey = (code_checksum, "python", "transformer")
    semantic_code_checksum = transformation_cache.syntactic_to_semantic_checksums.get(
        synkey
    )
    semantic_code_checksum = Checksum(semantic_code_checksum)
    if semantic_code_checksum:
        return semantic_code_checksum

    if code is None:
        code = get_buffer(code_checksum)
    if code is None:
        raise CacheMissError(code_checksum.hex())
    tree = ast.parse(code, filename="<None>")
    semcode = ast_dump(tree).encode()
    semantic_code_checksum = calculate_checksum(semcode, hex=False)
    _sem_code_cache[semantic_code_checksum] = semcode
    transformation_cache.syntactic_to_semantic_checksums[synkey] = (
        semantic_code_checksum
    )
    key = (semantic_code_checksum, "python", "transformer")
    cache = transformation_cache.semantic_to_syntactic_checksums
    if key not in cache:
        cache[key] = []
    if code_checksum not in cache[key]:
        cache[key].append(code_checksum)
        database.set_sem2syn(key, cache[key])

    return semantic_code_checksum


def _get_node_transformation_dependencies(node):
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

    from seamless.workflow.highlevel import Base, Cell, Module
    from seamless.workflow.highlevel.DeepCell import DeepCellBase

    language = node["language"]
    if language == "bash":
        raise NotImplementedError  # substitute bash code checksum, see rprod bash_transformation

    result_name = node["RESULT"]
    if node["language"] != "python":
        assert result_name == "result"
    assert result_name not in node["pins"]  # should have been checked by highlevel
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
        envbuf = serialize_sync(env, "plain")
        checksum = calculate_checksum(envbuf)
        cache_buffer(checksum, envbuf)
        transformation_dict["__env__"] = checksum.hex()

    meta = node.get("meta")
    if meta:
        transformation_dict["__meta__"] = meta
    node_pins = deepcopy(node["pins"])

    tf_pins = {}
    for pinname, pin in list(node_pins.items()):
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

        pin.pop("subcelltype", None)  # just to make sure...
        if celltype == "module":
            pin = {"celltype": "plain", "subcelltype": "module"}
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
                    "filesystem": {"mode": "directory", "optional": False},
                }
            elif celltype == "folder":
                pin = {
                    "celltype": "mixed",
                    "hash_pattern": {"*": "##"},
                    "filesystem": {"mode": "directory", "optional": True},
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
                checksum = Checksum(checksum)
                if not checksum:
                    raise ValueError(
                        f"Argument {pinname} (Cell {value}) has no checksum available"
                    )
                v = checksum
            elif isinstance(value, Transformation):
                v = value
            else:
                v = value

        transformation_dict[pinname] = (pin["celltype"], pin.get("subcelltype"), v)
    assert "code" in transformation_dict
    assert transformation_dict["code"][2] is not None, transformation_dict["code"]
    return transformation_dict


def _wait():
    from seamless.util.is_forked import is_forked

    global _has_lock
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
            tf_dunder,
            syntactic_cache,
            increfed,
            fingertip,
            scratch,
        ) in queued_transformations:
            if is_forked():
                # print(f"Delegate to parent: {transformation}, fingertip = {fingertip}, stack = {TRANSFORMATION_STACK}")
                assert transformation not in TRANSFORMATION_STACK
                _parent_process_queue.put(
                    (
                        7,
                        (
                            transformation,
                            tf_dunder,
                            syntactic_cache,
                            fingertip,
                            scratch,
                        ),
                    )
                )
        for (
            result_callback,
            transformation,
            transformation_dict,
            tf_dunder,
            syntactic_cache,
            increfed,
            fingertip,
            scratch,
        ) in queued_transformations:
            try:
                tf_checksum = Checksum(transformation)
                if is_forked():
                    while 1:
                        ###tf_checksum2, result_checksum, logs = _parent_process_response_queue.get(timeout=15) ###
                        tf_checksum2, result_checksum, logs = (
                            _parent_process_response_queue.get()
                        )
                        if tf_checksum2 != tf_checksum.hex():
                            _parent_process_response_queue.put(
                                (tf_checksum2, result_checksum, logs)
                            )
                            time.sleep(0.1)
                            continue
                        _parent_process_response_queue.task_done()
                        break
                    result_checksum = Checksum(result_checksum)
                    if result_checksum:
                        transformation_cache.register_known_transformation(
                            tf_checksum, result_checksum
                        )
                    transformation_cache.transformation_logs[tf_checksum] = logs
                else:
                    running_event_loop = asyncio.get_event_loop().is_running()
                    result_checksum = run_transformation(
                        transformation,
                        fingertip=fingertip,
                        new_event_loop=running_event_loop,
                        scratch=scratch,
                        tf_dunder=tf_dunder,
                    )
                    result_checksum = Checksum(result_checksum)

            finally:
                # For some reason, the logic here is different than for the async version
                # (see run_transformation_dict_async)
                temprefmanager.purge_group("imperative")
                if (
                    increfed
                    and Checksum(transformation) in transformation_cache.transformations
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


def cleanup():
    """is registered atexit by seamless.workflow.core, because it must run first"""
    for (
        _,
        transformation,
        transformation_dict,
        _,
        _,
        increfed,
        _,
        _,
    ) in _queued_transformations:
        # For some reason, the logic here is different than for the async version
        # (see run_transformation_dict_async)
        if (
            increfed
            and Checksum(transformation) in transformation_cache.transformations
        ):
            transformation_cache.decref_transformation(transformation_dict, increfed)
