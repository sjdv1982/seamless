# Author: Sjoerd de Vries
# Copyright (c) 2016-2022 INSERM, 2022 CNRS

# The MIT License (MIT)

# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
# SOFTWARE.

"""Context class to organize cells and workers hierarchically,
and its helper functions."""

# pylint: disable=too-many-lines

from __future__ import annotations
from typing import *
import traceback
from copy import deepcopy
from collections import namedtuple
import weakref
import itertools
import threading
import asyncio
import inspect
import functools
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED
from io import BytesIO
import json
from weakref import WeakSet
import atexit
import logging

logger = logging.getLogger("seamless")


def print_info(*args):
    """Logger function"""
    msg = " ".join([str(arg) for arg in args])
    logger.info(msg)


def print_warning(*args):
    """Logger function"""
    msg = " ".join([str(arg) for arg in args])
    logger.warning(msg)


def print_debug(*args):
    """Logger function"""
    msg = " ".join([str(arg) for arg in args])
    logger.debug(msg)


def print_error(*args):
    """Logger function"""
    msg = " ".join([str(arg) for arg in args])
    logger.error(msg)


from .Base import Base
from .HelpMixin import HelpMixin
from ..core.macro_mode import macro_mode_on, until_macro_mode_off
from ..core.context import StatusReport, context as core_context
from .assign import assign
from .proxy import Pull
from .. import copying
from ..vault import save_vault, load_vault

Graph = namedtuple("Graph", ("nodes", "connections", "params", "lib"))

_contexts: WeakSet = weakref.WeakSet()


def _get_auth_tasks(taskmanager):
    tasks = []
    for task in taskmanager.tasks:
        if isinstance(task, _auth_task_types):
            tasks.append(task)
    return tasks


def _run_in_mainthread(func):
    def func2(*args, **kwargs):
        ctx = args[0]
        manager = ctx._manager
        if threading.current_thread() != threading.main_thread():
            manager.taskmanager.add_synctask(func, args, kwargs, with_event=False)
        else:
            func(*args, **kwargs)

    functools.update_wrapper(func2, func)
    return func2


shareserver = None


def _get_status(
    parent: Context,
    children: dict[tuple[str, ...], Base],
    nodes: dict[tuple[str, ...], Any],
    path: tuple[str, ...],
) -> StatusReport | str:
    """Return the status of all direct children

    Children have been taken from .children, as well as all nodes in the nodegraph
    of type "context", creating a SubContext on the fly.

    Returns a StatusReport with the .status of each child that is doesn't have status OK.
    If there are no such children, return "Status: OK".
    """
    result = StatusReport()
    if path is not None:
        lp = len(path)
    all_children = itertools.chain(children.items(), nodes.items())
    for childname0, child in all_children:
        if path is not None:
            if childname0[:lp] != path:
                continue
            childname0 = childname0[lp:]
        if len(childname0) != 1:
            continue
        childname = childname0[0]
        if isinstance(child, dict):  # node
            if child["type"] != "context":
                continue
            subpath: tuple[str, ...]
            subpath = (childname,)
            if path is not None:
                subpath = path + subpath
            child = SubContext(parent, subpath)
        s = child.status
        if s != "Status: OK":
            result[childname] = s
    if len(result):
        return result
    else:
        return "Status: OK"


def _destroy_contexts():
    _cleanup()
    for context in _contexts:
        try:
            context._destroy()
        except Exception:
            pass


atexit.register(_destroy_contexts)


def _get_zip(buffer_dict):
    from ..core.cache.buffer_cache import empty_dict_checksum, empty_list_checksum
    archive = BytesIO()
    with ZipFile(archive, mode="w", compression=ZIP_DEFLATED) as zipf:
        for checksum in sorted(list(buffer_dict.keys())):
            if checksum in (empty_dict_checksum, empty_list_checksum):
                continue
            buffer = buffer_dict[checksum]
            info = ZipInfo(checksum, date_time=(1980, 1, 1, 0, 0, 0))
            zipf.writestr(info, buffer)
    result = archive.getvalue()
    archive.close()
    return result


class Context(Base, HelpMixin):
    """Context class. Organizes cells and workers hierarchically.

    Wrapper around a workflow graph, which can be serialized as JSON to a
    .seamless file.
    Changing the workflow topology (by adding/removing children or connections,
    or by changing celltypes) marks the context as "untranslated".
    Untranslated graphs can be translated explicitly, or implicitly
    (with the .compute method).
    Upon translation, wraps a a low-level context object (seamless.core.context).
    This context does all the work and holds all the data. Most of the methods
    and properties of the Seamless high-level classes (Cell, Transformer, etc.)
    are wrappers that interact with their low-level counterparts. Seamless
    low-level contexts accept value changes but not modifications in topology.


    Typical usage:
    ```python
    ctx = Context()
    ctx.a = 32   # equivalent to: ctx.a = Cell().set(32)
    def func(a, b):
        return a + b
    ctx.func = func   # equivalent to:
                      # ctx.func = Transformer(); ctx.func.set(func)
    ctx.func.a = ctx.a
    ctx.func.b = 16
    ctx.result = ctx.func.result
    ctx.compute()
    assert ctx.result.value == 48
    ```

    See http://sjdv1982.github.io/seamless/sphinx/html/context.html for documentation
    """

    _default_parameters = {"share_namespace": "ctx"}
    _translating = False
    _translate_count = 0
    _gen_context = None

    _runtime_graph = None
    # the graph as synthesized by pre-translating all LibInstances, overlaying onto the main graph

    _weak = False
    # True for autogenerated contexts that have no strong reference

    _live_share_namespace = None
    _destroyed: bool = False
    _environment: Optional[ContextEnvironment] = None
    _libroot = None
    _untranslatable = False
    _reverse_fallbacks: WeakSet = (
        WeakSet()
    )  # Fallback objects from other Contexts, that use a fallback cell in this Context

    _manager: Manager
    _graph: Graph
    _children: dict[tuple[str, ...], Base]
    _needs_translation: bool
    _parent: Any  # weakref.ref or lambda returning None
    _traitlets: dict[tuple[str, ...], SeamlessTraitlet]
    _observers: set
    _unbound_context: Any = None  # Optional[core.Context]
    _runtime_indices = {}

    @classmethod
    def from_graph(
        cls,
        graph: str | dict,
        manager: Optional[Manager],
        *,
        mounts: bool = True,
        shares: bool = True,
        share_namespace: Optional[str] = None,
        zip: Optional[str | bytes | ZipFile] = None  # pylint: disable=redefined-builtin
    ):
        """Construct a Context from a graph

        "graph" can be a file name or a JSON dict
        Normally, it has been generated with Context.save_graph / Context.get_graph

        "zip" can be a file name, zip-compressed bytes or a Python ZipFile object.
        Normally, it has been generated with Context.save_zip / Context.get_zip

        "manager": re-use the manager of a previous context.
        The manager controls caching and execution.

        "mounts": mount cells and pins to the file system, as specified in the graph.

        "shares": share cells over HTTP, as specified in the graph

        "share_namespace": The namespace to use for HTTP sharing ("ctx"by default)

        """
        self = cls(manager=manager)
        if zip is not None:
            self.add_zip(zip)
        if share_namespace is not None:
            self.share_namespace = share_namespace
        self.set_graph(graph, mounts=mounts, shares=shares)
        return self

    def set_graph(self, graph, *, mounts: bool = True, shares: bool = True):
        """Set the graph of the Context

        "graph" can be a file name or a JSON dict
        Normally, it has been generated with Context.save_graph / Context.get_graph

        "mounts": mount cells and pins to the file system, as specified in the graph.

        "shares": share cells over HTTP, as specified in the graph

        """
        from . import nodeclasses
        from ..midlevel.graph_convert import graph_convert

        for child in self._children.values():
            if isinstance(child, Transformer):
                if child.debug.mode is not None:
                    msg = "Cannot delete {} in debug mode"
                    raise Exception(msg.format(child))
        if isinstance(graph, str):
            graph_file = graph
            with open(graph_file) as f:
                graph = json.load(f)
        graph = graph_convert(graph, self)
        nodes = {}
        self._children.clear()
        for node in graph["nodes"]:
            p = tuple(node["path"])
            if not mounts:
                node.pop("mount", None)
            if not shares:
                node.pop("share", None)
            node["path"] = p
            nodes[p] = node
            nodetype = node["type"]
            if nodetype == "libinstance":
                continue
            nodecls = nodeclasses[nodetype]
            child = nodecls(parent=self, path=p)
            if nodetype in ("cell", "transformer", "macro"):
                node["UNTRANSLATED"] = True
        connections = graph["connections"]
        for con in connections:
            if con["type"] == "connection":
                con["source"] = tuple(con["source"])
                con["target"] = tuple(con["target"])
            elif con["type"] == "link":
                con["first"] = tuple(con["first"])
                con["second"] = tuple(con["second"])
        params = deepcopy(self._default_parameters)
        params.update(graph["params"])
        lib0 = graph.get("lib", [])
        self._graph = Graph(nodes, connections, params, {})
        for l in lib0:
            path = tuple(l["path"])
            l["path"] = path
            self._set_lib(path, l)
        env = graph.get("environment", None)
        self.environment._load(env)
        self._translate()
        return self

    def __init__(self, manager: Optional[Manager] = None):
        """Create a new Seamless context

        "manager": re-use the manager of a previous context.
        The manager controls caching and execution.
        """
        super().__init__(None, ())

        if manager is not None:
            assert isinstance(manager, Manager), type(manager)
            self._manager = manager
        else:
            self._manager = Manager()
        self._manager._highlevel_refs += 1
        self._graph = Graph({}, [], {}, {})
        self._graph.params.update(deepcopy(self._default_parameters))
        self._children = {}
        self._needs_translation = True
        self._parent = weakref.ref(self)
        self._traitlets = {}
        self._observers = set()
        self._environment = ContextEnvironment(self)
        _contexts.add(self)

    def _get_node(self, path):
        try:
            return self._graph[0][path]
        except KeyError:
            try:
                return self._runtime_graph.nodes[path]
            except (KeyError, AttributeError):
                raise KeyError(path) from None

    def _get_from_path(self, path: tuple[str, ...]):
        """Return the child under "path".
        e.g. ctx._get_from_path(("a", "b")) return ctx.a.b
        First, a child is looked up in ._children
        If that fails, "path" is looked up in the graph nodes
        """
        child = self._children.get(path)
        if child is not None:
            return child
        node = self._graph[0].get(path)
        if node is not None:
            if node["type"] == "libinstance":
                li = LibInstance(self, path=path)
                li._bound = weakref.ref(self)
                return li
            if node["type"] != "context":
                raise AttributeError(
                    "Node {} is not a Context, and not a child of this Context".format(
                        path
                    )
                )
            return SubContext(self, path)
        attr: Any
        if len(path) == 1:
            attr = path[0]
        else:
            attr = path
        raise AttributeError(attr)

    def __getitem__(self, attr):
        if not isinstance(attr, str):
            raise KeyError(attr)
        return getattr(self, attr)

    def __setitem__(self, attr, value):
        if not isinstance(attr, str):
            raise KeyError(attr)
        setattr(self, attr, value)

    def __getattribute__(self, attr):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if hasattr(type(self), attr) or attr in self.__dict__ or attr == "path":
            return super().__getattribute__(attr)
        path = (attr,)
        try:
            return self._get_from_path(path)
        except AttributeError:
            raise AttributeError(attr) from None

    def __setattr__(self, attr, value):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        members = {k: v for k, v in inspect.getmembers(type(self))}
        if attr in members and isinstance(members[attr], property):
            return object.__setattr__(self, attr, value)
        attr2 = (attr,)
        if isinstance(value, (Transformer, Macro)):
            if value._parent is None:
                self._graph[0][attr2] = value
                self._set_child(attr2, value)
                value._init(self, attr2)
                self._translate()
            else:
                assign(self, attr2, value)
        elif isinstance(value, Pull):
            value._proxy._pull_source(attr2)
        else:
            assign(self, attr2, value)

    def __delattr__(self, attr):
        if attr.startswith("_"):
            return super().__delattr__(attr)
        self._destroy_path((attr,))

    def _add_traitlet(self, path, trigger):
        traitlet = self._traitlets.get(path)
        if traitlet is not None:
            return traitlet
        traitlet = SeamlessTraitlet(value=None)
        traitlet.parent = weakref.ref(self)
        traitlet.path = path
        if trigger:
            traitlet._connect_seamless()
        self._traitlets[path] = traitlet
        self._translate()
        return traitlet

    def compute(self, timeout: Optional[float] = None, report: float = 2):
        """Block until no more computation is required.

        This means that all cells and transformers have either been computed,
        or they have an error, or they have unsatisfied upstream dependencies.

        The graph is first (re-)translated, if necessary.

        This function can only be invoked if no event loop is running,
        i.e. under python or ipython, but not in a Jupyter kernel.
        """
        from seamless import verify_sync_compute

        verify_sync_compute()
        self.translate()
        return self._gen_context.compute(timeout, report)

    async def computation(self, timeout: Optional[float] = None, report: float = 2):
        """Block until no more computation is required.

        This means that all cells and transformers have either been computed,
        or they have an error, or they have unsatisfied upstream dependencies.

        The graph is first (re-)translated, if necessary.
        """
        await self.translation()
        await self._gen_context.computation(timeout, report)

    @property
    def self(self):
        """Return a wrapper where the children are not directly accessible.

        By default, a Cell called "compute" will cause "ctx.compute" to return
        the Cell. This is problematic if you want to access the method compute().
        This can be done using ctx.self.compute()

        NOTE: experimental, requires more testing
        """
        attributelist = [k for k in type(self).__dict__ if not k.startswith("_")]
        attributelist += [k for k in HelpMixin.__dict__ if not k.startswith("_")]
        return SelfWrapper(self, attributelist)

    @property
    def environment(self):
        """Return the global execution environment of the context"""
        return self._environment

    def _translate(self):
        if self._untranslatable:
            return
        self._needs_translation = True

    def translate(self, force: bool = False):
        """(Re-)translate the graph.
        The graph is translated to a low-level, computable form
        (seamless.core). After translation, return immediately,
        although computation will start automatically.

        If force=True, translation will happen even though no
        change in topology or celltype was detected.

        This function can only be invoked if no event loop is running,
        i.e. under python or ipython, but not in a Jupyter kernel.
        """
        from seamless import verify_sync_translate

        if self._untranslatable:
            raise Exception("Context is untranslatable")
        if not force and not self._needs_translation:
            return
        verify_sync_translate()
        self._wait_for_auth_tasks("the graph is re-translated")
        return self._do_translate(force=force)

    async def translation(self, force: bool = False):
        """(Re-)translate the graph.
        The graph is translated to a low-level, computable form
        (seamless.core). After translation, return immediately,
        although computation will start automatically.

        If force=True, translation will happen even though no
        change in topology or celltype was detected.
        """
        if self._untranslatable:
            raise Exception("Context is untranslatable")
        await self._wait_for_auth_tasks_async("the graph is re-translated")
        return await self._do_translate_async(force=force)

    @property
    def share_namespace(self):
        """The preferred namespace for sharing cells by the HTTP server

        Cells are shared under:
         http://<shareserver URL>/<live_share_namespace>/<cell path>

        The live share namespace is in principle equal to the share namespace,
        but if it is already taken, a number will be added to it (ctx1, ctx2, etc.)

        Default: "ctx"
        """
        return self._graph.params["share_namespace"]

    @share_namespace.setter
    def share_namespace(self, value):
        if not isinstance(value, str):
            raise TypeError(value)
        self._graph.params["share_namespace"] = value
        self._live_share_namespace = None

    @property
    def live_share_namespace(self):
        """The actual namespace for sharing cells by the HTTP server

        Cells are shared under:
         http://<shareserver URL>/<live_share_namespace>/<cell path>

        The live share namespace is in principle equal to the share namespace,
        but if it is already taken, a number will be added to it (ctx1, ctx2, etc.)

        Default: "ctx"
        """
        return self._live_share_namespace

    def _get_graph_dict(self, copy: bool) -> dict[str, Any]:
        """Obtain the graph in dict format, ready to be serialized.

        First give pending auth tasks (independent checksums being set)
        some time to finish.
        Also try to fill in TEMP values (e.g. from newly created
        untranslated cells).

        Finally, the elements of the dict are a fairly straightforward
        extraction of self._graph.
        """
        self._wait_for_auth_tasks("the graph is being obtained")
        try:
            self._translating = True
            manager = self._manager
            copying.fill_checksums(manager, self._graph.nodes)
        finally:
            self._translating = False
        nodes, connections, params, lib = self._graph
        nodes = [v for k, v in sorted(nodes.items(), key=lambda kv: kv[0])]
        lib = [v for k, v in sorted(lib.items(), key=lambda kv: kv[0])]
        if copy:
            connections = deepcopy(connections)
            nodes = deepcopy(nodes)
            params = deepcopy(params)
            lib = deepcopy(lib)
        graph = {
            "__seamless__": "0.11",
            "nodes": nodes,
            "connections": connections,
            "params": params,
            "lib": lib,
        }
        env = self.environment._save()
        if env is not None:
            graph["environment"] = env
        return graph

    async def _get_graph_dict_async(self, copy: bool) -> dict[str, Any]:
        """Obtain the graph in dict format, ready to be serialized.

        Async version of _get_graph_dict.
        """
        await self._wait_for_auth_tasks_async("the graph is being obtained")
        try:
            self._translating = True
            manager = self._manager
            copying.fill_checksums(manager, self._graph.nodes)
        finally:
            self._translating = False
        nodes, connections, params, lib = self._graph
        nodes = [v for k, v in sorted(nodes.items(), key=lambda kv: kv[0])]
        lib = [v for k, v in sorted(lib.items(), key=lambda kv: kv[0])]
        if copy:
            connections = deepcopy(connections)
            nodes = deepcopy(nodes)
            params = deepcopy(params)
            lib = deepcopy(lib)
        graph = {
            "__seamless__": "0.11",
            "nodes": nodes,
            "connections": connections,
            "params": params,
            "lib": lib,
        }
        env = self.environment._save()
        if env is not None:
            graph["environment"] = env
        return graph

    def get_graph(self, runtime: bool = False) -> dict[str, Any]:
        """Return the graph in JSON format.

        "runtime": The graph is returned after Library/LibInstance/Macro
        transformations of the graph.
        """
        graph_dict = self._get_graph_dict(copy=True)
        if not runtime:
            return graph_dict
        else:
            # self._get_graph_dict still needs to be run
            pass

        graph0 = deepcopy(self._runtime_graph)
        if graph0 is None:
            return None

        connections = deepcopy(graph0.connections)
        nodes = deepcopy(graph0.nodes)
        params = deepcopy(graph0.params)
        lib = deepcopy(graph0.lib)
        graph = {
            "nodes": [node for node in nodes.values()],
            "connections": connections,
            "params": params,
            "lib": lib,
        }
        return graph

    async def _get_graph_async(self, *args, **kwargs):
        # Legacy method
        return self.get_graph()
        
    def save_graph(self, filename: str):
        """Save the graph in JSON format."""
        graph = self.get_graph()
        with open(filename, "w") as f:
            json.dump(graph, f, sort_keys=True, indent=2)

    def get_zip(self, with_libraries: bool = True) -> bytes:
        """Obtain the checksum-to-buffer cache for the current graph.

        The cache is returned as zipped bytes.
        """
        # TODO: option to not follow deep cell checksums (currently, they are always followed)
        force = self._gen_context is None
        self._wait_for_auth_tasks("the graph buffers are obtained for zip")
        self._do_translate(force=force)
        graph = self.get_graph()
        checksums = copying.get_graph_checksums(
            graph, with_libraries, with_annotations=False
        )
        manager = self._manager
        buffer_dict = copying.get_buffer_dict_sync(manager, checksums)
        return _get_zip(buffer_dict)

    async def get_zip_async(self, with_libraries: bool = True) -> bytes:
        """Obtain the checksum-to-buffer cache for the current graph

        The cache is returned as zipped bytes.
        """
        # TODO: option to not follow deep cell checksums (currently, they are always followed)
        force = self._gen_context is None
        await self._wait_for_auth_tasks_async("the graph buffers are obtained for zip")
        self._do_translate(force=force)
        graph = self.get_graph()
        checksums = copying.get_graph_checksums(
            graph, with_libraries, with_annotations=False
        )
        manager = self._manager
        buffer_dict = await copying.get_buffer_dict(manager, checksums)
        return _get_zip(buffer_dict)

    def save_zip(self, filename: str):
        """Save the checksum-to-buffer cache for the current graph.

        The cache is saved to "filename", which should be a .zip file.
        """
        zipd = self.get_zip()
        with open(filename, "wb") as f:
            f.write(zipd)

    async def save_zip_async(self, filename: str):
        """Save the checksum-to-buffer cache for the current graph.

        The cache is saved to "filename", which should be a .zip file.
        """
        zipd = self.get_zip_async()
        with open(filename, "wb") as f:
            f.write(zipd)

    def save_vault(self, dirname: str, with_libraries: bool = True):
        """Save the checksum-to-buffer cache for the current graph in a vault directory"""
        # TODO: option to not follow deep cell checksums (currently, they are always followed)
        force = self._gen_context is None
        self._wait_for_auth_tasks("the graph buffers are obtained for zip")
        self._do_translate(force=force)
        if self._gen_context is not None:
            # capture from the low level
            annotated_checksums_low = {}
            self._gen_context._update_annotated_checksums(annotated_checksums_low)

        # update from the high level
        graph = self.get_graph()
        annotated_checksums_high = copying.get_graph_checksums(
            graph, with_libraries, with_annotations=True
        )
        

        annotated_checksums = {}
        annotated_checksums.update(annotated_checksums_low)
        annotated_checksums.update({c[0]: not c[1] for c in annotated_checksums_high})
        annotated_checksums = [(checksum, not has_independence) for checksum, has_independence in annotated_checksums.items()]

        manager = self._manager
        checksums = [c[0] for c in annotated_checksums]
        buffer_dict = copying.get_buffer_dict_sync(manager, checksums)
        save_vault(dirname, annotated_checksums, buffer_dict)

    def _set_child(self, path, child):
        if self._translating:
            return
        self._children[path] = child

    def _set_lib(self, path, lib):
        """Insert a library "lib" into self._graph.lib.
        Privileged method to be used by "friendly" code.

        Library "lib" must be a dict that corresponds to an includable Library.
        See Library.include() for an informative example.
        "lib" can also be None, in which case any existing lib is removed.

        In addition to storing "lib" in self._graph.lib, the checksums of the
        lib are extracted and added to the buffer cache.
        Conversely, the checksums from the existing lib (if any) are removed
        from the cache.
        """
        old_lib = self._graph.lib.get(path)
        if lib is not None:
            self._graph.lib[path] = lib
            checksums = copying.get_checksums(
                lib["graph"]["nodes"],
                lib["graph"]["connections"],
                with_annotations=False,
            )
            for checksum in checksums:
                buffer_cache.incref(bytes.fromhex(checksum), True)
        else:
            if old_lib is not None:
                self._graph.lib.pop(path)
        if old_lib is not None:
            old_checksums = copying.get_checksums(
                old_lib["graph"]["nodes"], [], with_annotations=False
            )
            for old_checksum in old_checksums:
                buffer_cache.decref(bytes.fromhex(old_checksum))

    def add_zip(self, zip, incref: bool = False):  # pylint: disable=redefined-builtin
        """Add entries from "zip" to the checksum-to-buffer cache.

        "zip" can be a file name, zip-compressed bytes or a Python ZipFile object.
        Normally, it has been generated with Context.save_zip / Context.get_zip

        Note that caching is temporary and entries will be removed after some time
        if no element (cell, expression, or high-level library) holds their checksum
        This can be overridden with "incref=True" (not recommended for long-living contexts)

        """
        if self._gen_context is None:
            self._do_translate(force=True)
        manager = self._manager
        if isinstance(zip, bytes):
            archive = BytesIO(zip)
            zipfile = ZipFile(archive, "r")
        elif isinstance(zip, str):
            zipfile = ZipFile(zip, "r")
        elif isinstance(zip, ZipFile):
            zipfile = zip
        elif hasattr(zip, "read") and callable(zip.read):
            zipfile = ZipFile(zip, "r")
        else:
            raise TypeError(type(zip))
        return copying.add_zip(manager, zipfile, incref=incref)

    def load_vault(self, vault_directory: str, incref: bool = False):
        """Load the contents of a vault directory in the checksum-to-buffer cache.

        Normally, the vault has been generated with Context.save_vault.

        Note that caching is temporary and entries will be removed after some time
        if no element (cell, expression, or high-level library) holds their checksum
        This can be overridden with "incref=True" (not recommended for long-living contexts).

        """
        if self._gen_context is None:
            self._do_translate(force=True)
        return load_vault(vault_directory, incref=incref)

    def include(self, lib: Library, only_zip: bool = False, full_path: bool = False):
        """Include a library in the graph.

        A library (seamless.highlevel.Library) must be included before
        library instances (seamless.highlevel.LibInstance) can be constructed
        using ctx.lib
        """

        if not isinstance(lib, Library):
            raise TypeError(type(lib))
        if only_zip:
            lib.include_zip(self)
        else:
            lib.include(self, full_path=full_path)
        self._translate()

    def _wait_for_auth_tasks(self, what_happens_text):
        """Wait up to 10 seconds for auth tasks to complete.

        Auth tasks are those that modify independent checksums of the workflow.
        i.e. the checksums that are input parameters (including code) and are
        not computed by a transformation, conversion, etc.

        Auth tasks are normally very quick, as they don't involve much
        computation.
        It is assumed (and printed out) that any auth tasks that have not
        completed after 10 seconds will be canceled.
        """
        if self._gen_context is not None and not self._libroot and not asyncio.get_event_loop().is_running():
            taskmanager = self._gen_context._get_manager().taskmanager
            taskmanager.compute(timeout=10, report=2, get_tasks_func=_get_auth_tasks)
            auth_lost_cells = set()
            for task in taskmanager.tasks:
                if not isinstance(task, _auth_task_types):
                    continue
                if task._canceled:
                    continue
                auth_lost_cells.add(task.dependencies[0])
                task.cancel()

            if len(auth_lost_cells):
                warn = """WARNING: the following cells had their authoritative value
under modification while %s.
    %s
These modifications have been CANCELED.""" % (
                    what_happens_text,
                    list(auth_lost_cells),
                )
                print(warn)

    async def _wait_for_auth_tasks_async(self, what_happens_text):
        """Async version of _wait_for_auth_tasks."""
        if self._gen_context is not None and not self._libroot:
            taskmanager = self._gen_context._get_manager().taskmanager
            await taskmanager.computation(
                timeout=10, report=2, get_tasks_func=_get_auth_tasks
            )
            auth_lost_cells = set()
            for task in taskmanager.tasks:
                if not isinstance(task, _auth_task_types):
                    continue
                if task._canceled:
                    continue
                auth_lost_cells.add(task.dependencies[0])
                task.cancel()

            if len(auth_lost_cells):
                # pylint: disable=line-too-long
                warn = """WARNING: the following cells had their authoritative value under modification while %s
    These modifications have been CANCELED:
    %s""" % (
                    what_happens_text,
                    list(auth_lost_cells),
                )
                print(warn)

    @_run_in_mainthread
    def _do_translate(self, force=False):
        graph0 = self._get_graph_dict(copy=False)
        return self._do_translate2(graph0, force=force)

    async def _do_translate_async(self, force=False):
        assert threading.current_thread() == threading.main_thread()
        graph0 = await self._get_graph_dict_async(copy=False)
        await until_macro_mode_off()
        return self._do_translate2(graph0, force=force)

    def _do_translate2(self, graph0, force):
        """Translates a graph dict (graph0) into a low-level representation.

        Called from _do_translateXXX, where a graph dict is obtained.
        No-op if no translation is needed, unless force=True.
        No-op if translation is already ongoing.
        Translation is forbidden while transformers are in debug mode.

        NOTE: This function is sync, and it is crucial that it is.
        While this function is running, the Context state is rather fragile.
        The function does not *quite* happen in sync (the async loop may
        run shortly during translation), which is why there is a kludge
        (see below).

        Steps:

        - Validate the global context .environment .

        - Pre-translate the graph. This means evaluating LibInstances and
          merging their sub-graphs into the graph.
          The pre-translated graph is set to ._runtime_graph.
          It is tabulated which nodes of the previous runtime graph are no
          longer there, but this matters only for debugging-mode transformers.

        - The low-level representation (seamless.core.context.Context) is
        stored in ._gen_context. Any previous representation is first
        completely destroyed. This must succeed.

        - Necessary functions from the translation machinery (seamless.midlevel)
        are imported only if needed.

        - Low-level macro mode is entered. A new low-level context is constructed.
        It receives our manager (._manager) as its manager, so it can re-use
        buffer caches, share server, mounting, etc.
        Note that the low-level context is an "unbound" state until macro mode ends.

        - The actual translation is performed.

        - The "UNTRANSLATED" marker is removed from every node in the graph dict.

        - Macro mode terminates. There is now a "bound" context, that is now
        assigned to ._gen_context. This also receives a weakref to self, i.e. the
        high level context. This weakref is necessary if a (low-level) macro
        adds an embedded high-level context (seamless.core.HighLevelContext)
        object. This embedded high-level context must link up with self to
        integrate itself temporarily into the children and (runtime) node graph.

        - Second stage of the translation starts.

        - Observers (functions, not traitlets) are set.

        - Cell fallbacks are activated.

        - Traitlets are connected.

        - Second stage of the translation ends.
        """
        from ..midlevel.translate import translate, import_before_translate
        from ..midlevel.pretranslate import pretranslate

        if not force and not self._needs_translation:
            return
        if self._translating:
            return
        for child in self._children.values():
            if isinstance(child, Transformer):
                if child.debug.mode is not None:
                    msg = "Cannot translate while {} in debug mode"
                    raise Exception(msg.format(child))
        env = self.environment._parse_and_validate()
        graph = pretranslate(self, graph0)
        old_runtime_nodes = set()
        if self._runtime_graph is not None:
            old_nodes = set(self._graph.nodes)
            old_runtime_nodes = set(self._runtime_graph.nodes)
            old_runtime_nodes = old_runtime_nodes.difference(old_nodes)
        if graph is not graph0:
            libinstance_nodes = {node["path"]: node for node in graph["nodes"]}
            self._runtime_graph = Graph(
                libinstance_nodes, graph["connections"], graph["params"], graph["lib"]
            )
        else:
            graph0 = deepcopy(graph0)
            self._runtime_graph = Graph(
                {node["path"]: node for node in graph0["nodes"]},
                graph0["connections"],
                graph0["params"],
                graph0["lib"],
            )

        self._translate_count += 1
        livegraph = self._manager.livegraph
        ok = False
        try:
            # pylint: disable=pointless-string-statement
            self._translating = True
            if self._gen_context is not None:
                self._gen_context.destroy()
                print_info("*" * 30 + "DESTROYED BEFORE TRANSLATE" + "*" * 30)
                ok1 = self._manager.livegraph.check_destroyed()
                ok2 = self._manager.taskmanager.check_destroyed()
                if not ok1 or not ok2:
                    raise Exception(
                        "Cannot re-translate, since clean-up of old context was incomplete"
                    )
            import_before_translate(graph)
            """ KLUDGE
            The translation process does NOT happen in one async step; it will start launching tasks
            and those tasks will be run.
            This is a problem for the high level observers, that will miss checksum updates
             because they are connected only in the next step.
            We must hold all observations during translation, and flush them afterwards
            """
            livegraph._hold_observations = True
            with macro_mode_on():
                ub_ctx = core_context(toplevel=True, manager=self._manager)
                ub_ctx._compilers = env["compilers"]
                ub_ctx._languages = env["languages"]
                self._unbound_context = ub_ctx
                ub_ctx._root_highlevel_context = weakref.ref(self)
                # print("TRANSLATE", self)
                translate(graph, ub_ctx, self.environment)
                nodedict = {node["path"]: node for node in graph["nodes"]}
                nodedict0 = {node["path"]: node for node in graph0["nodes"]}
                for path in nodedict:
                    node = nodedict[path]
                    node0 = nodedict0.get(path)
                    if node0 is not None and node is not node0:
                        node0.pop("UNTRANSLATED", None)
                        node0.pop("UNSHARE", None)
            self._gen_context = ub_ctx._bound
            self._gen_context._root_highlevel_context = weakref.ref(self)
            assert self._gen_context._get_manager() is self._manager
            self._connect_share()
            ok = True
            for child_path, child in self._children.items():
                if child_path in old_runtime_nodes:
                    continue
                if isinstance(child, Transformer):
                    child.debug.on_translate()
        finally:
            if not ok:
                livegraph._hold_observations = False
            self._translating = False
            self._unbound_context = None
            needs_translation = False
            for node in graph0["nodes"]:
                if isinstance(node, dict) and node.get("UNTRANSLATED"):
                    needs_translation = True
                    break
            self._needs_translation = needs_translation

        try:
            livegraph._hold_observations = True
            self._translating = True
            for path, child in self._children.items():
                if isinstance(
                    child, (Cell, Transformer, Macro, Module, DeepCell, DeepFolderCell)
                ):
                    try:
                        child._set_observers()
                    except Exception:
                        traceback.print_exc()
                elif isinstance(child, (PinWrapper, Link)):
                    continue
                else:
                    raise TypeError(type(child))

            self._activate_fallbacks()
            for traitlet in self._traitlets.values():
                try:
                    traitlet._connect_seamless()
                except Exception:
                    traceback.print_exc()

        finally:
            livegraph._hold_observations = False
            print_info("*" * 30 + "TRANSLATE COMPLETE" + "*" * 30)
            self._translating = False

        livegraph._flush_observations()

    def _activate_fallbacks(self):
        """Activate all fallbacks of all cells in the Context"""
        for fallback in self._reverse_fallbacks:
            fallback._activate()
        for cell in self._children.values():
            if not isinstance(cell, Cell):
                continue
            fallback = cell._fallback
            if fallback is not None:
                fallback._activate()

    def _get_shares(self):
        shares = {}
        for path, node in self._graph.nodes.items():
            if node["type"] not in ("cell", "deepcell", "deepfoldercell"):
                continue
            share = node.get("share")
            if share is not None:
                shares[path] = share
        if not len(shares):
            return None
        return shares

    def _connect_share(self):
        """Invoke .share on newly created cells.

        This is to be invoked right after translation.
        Only for cells that have a "share" entry in their graph node dict.
        The shareserver is started, if not running already.
        """
        shares = self._get_shares()
        if shares is None:
            return
        from ..core import StructuredCell, Cell as core_cell

        global shareserver
        from .. import shareserver as shareserver_

        shareserver = shareserver_
        from ..core.share import sharemanager

        shareserver.start()
        if self._live_share_namespace is None:
            self._live_share_namespace = sharemanager.new_namespace(
                self._manager, name=self.share_namespace, share_evaluate=False
            )
        for path, shareparams in shares.items():
            hcell = self._children[path]
            if isinstance(hcell, (DeepCell, DeepFolderCell)):
                sharepath = shareparams["path"]
                if sharepath is None:
                    sharepath = "/".join(path)
                toplevel = shareparams.get("toplevel", False)
                cell1 = hcell._get_context().options
                sharepath1 = sharepath + "/OPTIONS"
                cell1.share(
                    sharepath1,
                    readonly=False,
                    mimetype="application/json",
                    toplevel=toplevel,
                    cellname=cell1._format_path(),
                )
                cell2 = hcell._get_context().selected_option
                sharepath2 = sharepath + "/SELECTED_OPTION"
                cell2.share(
                    sharepath2,
                    readonly=False,
                    mimetype="text/plain",
                    toplevel=toplevel,
                    cellname=cell2._format_path(),
                )

                continue
            elif not isinstance(hcell, Cell):
                raise NotImplementedError(type(hcell))
            cell = hcell._get_cell()
            if isinstance(cell, StructuredCell):
                pass
            elif isinstance(cell, core_cell):
                pass
            else:
                raise TypeError(cell)
            sharepath = shareparams["path"]
            readonly = shareparams["readonly"]
            mimetype = hcell.mimetype
            toplevel = shareparams.get("toplevel", False)
            cell.share(
                sharepath,
                readonly,
                mimetype=mimetype,
                toplevel=toplevel,
                cellname="." + ".".join(path),
            )

    def _rename_path(self, path, newpath):
        # TODO: renaming
        raise NotImplementedError

    def _add_runtime_index(self, path, nodepathlist, connections):
        ind = self._runtime_indices
        for pp in path[:-1]:
            ind2 = ind.get(pp)
            if ind2 is None:
                ind2 = {}, None, None
                ind[pp] = ind2
            ind = ind2[0]
        pp = path[-1]
        if pp in ind:
            d = ind[pp][0]
        else:
            d = {}
        ind[pp] = d, nodepathlist, connections

    def _destroy_path(self, path, runtime=False, fast=False):
        """Destroy the child listed under "path".

        "path" can also refer to a subcontext.
        In fact, all children whose path starts with "path"
        are destroyed.

        Children are removed from the workflow graph nodes as well.
        Connections that involve destroyed children are removed as well.

        Transformers in debug mode cannot be destroyed.
        """
        if fast:
            assert runtime
        graph = self._graph
        if runtime:
            if self._runtime_graph is None:
                return
            graph = self._runtime_graph
        nodes = graph.nodes
        lp = len(path)
        if fast:
            nodes_to_remove = []
            connections_to_remove = []

            def walk(ind):
                for sub, nodes_to_remove0, connections_to_remove0 in ind.values():
                    nodes_to_remove.extend(nodes_to_remove0)
                    connections_to_remove.extend(connections_to_remove0)
                    walk(sub)

            ind = self._runtime_indices
            for pp in path[:-1]:
                #print(pp, ind.keys())
                ind2 = ind.get(pp)
                if ind2 is None:
                    ind = None
                    break
                ind = ind2[0]
            pp = path[-1]
            if ind is not None:
                ind2 = ind.pop(pp, None)
                if ind2 is not None:
                    sub, nodes_to_remove0, connections_to_remove0 = ind2
                    nodes_to_remove.extend(nodes_to_remove0)
                    connections_to_remove.extend(connections_to_remove0)
                    walk(sub)
        else:            
            # The following line takes an enormous amount for complex graphs!
            nodes_to_remove = [p for p in nodes.keys() if p[:lp] == path]
        for p in nodes_to_remove:
            child = self._children.get(p)
            if isinstance(child, Transformer):
                if child.debug.mode is not None:
                    msg = "Cannot destroy {} in debug mode"
                    raise Exception(msg.format(child))

            nodes.pop(p, None)
            self._children.pop(p, None)
            self._traitlets.pop(p, None)
        
        if not runtime and nodes_to_remove:
            self._translate()

        if fast:
            removed = len(connections_to_remove)
            connections = self._runtime_graph[1]
            for con in connections_to_remove:
                try:
                    connections.remove(con)
                except ValueError:
                    pass
        else:
            removed = self.remove_connections(path, runtime=runtime)
        if removed and not runtime:
            self._translate()

    @property
    def status(self) -> dict | str:
        """The computation status of the context
        Returns a dictionary containing the status of all direct children that are not OK.
        If all children are OK, returns "Status: OK"
        """
        nodes, _, _, _ = self._graph
        return _get_status(self, self._children, nodes, path=None)

    @property
    def lib(self):
        """Returns the libraries that were included in the graph"""
        from .library.include import IncludedLibraryContainer

        libroot = self._libroot
        if libroot is None:
            libroot = self
        return IncludedLibraryContainer(libroot, ())

    def resolve(self, checksum, celltype=None):
        """Returns the data buffer that corresponds to the checksum.
        If celltype is provided, a value is returned instead

        The checksum must be a SHA3-256 hash, as hex string or as bytes"""
        return self._manager.resolve(checksum, celltype=celltype, copy=True)

    def observe(
        self, path, callback, polling_interval, observe_none=False, params=None
    ):
        """Observe attributes of the context, analogous to Cell.observe."""

        observer = PollingObserver(
            self,
            path,
            callback,
            polling_interval,
            observe_none=observe_none,
            params=params,
        )
        self._observers.add(observer)
        return observer

    def unobserve(self, path=()):
        """Analogous to Cell.unobserve"""
        lp = len(path)
        for obs in list(self._observers):
            if obs.path[:lp] == path:
                self._observers.remove(obs)

    def _get_libs(self, path):
        libroot = self._libroot
        if libroot is None:
            libroot = self
        lib = libroot._graph.lib
        lp = len(path)
        result = {k[lp:]: v for k, v in lib.items() if len(k) > lp and k[:lp] == path}
        return result

    def _get_lib(self, path):
        libroot = self._libroot
        if libroot is None:
            libroot = self
        return libroot._graph.lib[tuple(path)]

    def remove_connections(self, path, *, runtime=False, endpoint="both", match="sub"):
        """Remove all connections/links with source or target matching path.

        "endpoint" can be "source", "target", "connection", "link" or "all".

        With endpoint "source", only remove connections where the source matches path.
        Don't remove links.

        With endpoint "target", only remove connections where the target matches path.
        Don't remove links.

        With endpoint "both", only remove connections where source or target matches path.
        Don't remove links.

        With endpoint "link", remove links where "first" or "second" matches path.
        Don't remove connections

        "match" can be "super", "exact", or "sub".

        If "super", only paths P that are shorter or equal to "path" are matched.
        The start of P must be identical to "path"

        If "exact", only paths P that are equal to "path" are matched.

        If "sub", only paths that are longer or equal to "path" are matched.
        The start of "path" must be identical to P.

        If "all", all longer and shorter paths are matched.
        """
        assert endpoint in ("source", "target", "both", "link", "all")
        assert match in ("super", "sub", "exact", "all")
        lp = len(path)

        def matches(p):
            if match == "exact":
                return p == path
            elif match == "super":
                return path[: len(p)] == p
            elif match == "sub":
                return p[:lp] == path
            else:  # all
                return p[:lp] == path or path[: len(p)] == p

        def keep_con(con):
            if con["type"] == "link":
                if endpoint not in ("link", "all"):
                    return True
                first = con["first"]
                if matches(first):
                    return False
                second = con["second"]
                if matches(second):
                    return False
                return True
            else:
                csource = con["source"]
                if endpoint in ("source", "both", "all"):
                    if matches(csource):
                        return False
                ctarget = con["target"]
                if endpoint in ("target", "both", "all"):
                    if matches(ctarget):
                        return False
                return True

        connections = self._graph[1]
        if runtime:
            connections = self._runtime_graph[1]
        new_connections = list(filter(keep_con, connections))
        any_removed = len(new_connections) < len(connections)
        connections[:] = new_connections
        return any_removed

    @property
    def webunits(self):
        from .WebunitWrapper import WebunitWrapper
        return WebunitWrapper(self)

    def link(self, first, second):
        """Create a bidirectional link between the first and second cell.

        Both cells must be authoritative (independent).
        """
        link = Link(self, first=first, second=second)
        connections = self._graph.connections
        connections.append(link._node)
        self._translate()

    def unlink(self, first, second):
        """Remove a bidirectional link between the first and second cell.
        (If it exists).
        Returns True if a link was removed
        """
        link = Link(self, first=first, second=second)
        try:
            link.remove()
        except ValueError:
            return False
        self._translate()
        return True

    def get_links(self):
        """Get all Link (bidirectional cell-cell) connections."""
        connections = self._graph.connections
        result = []
        for node in connections:
            if node["type"] == "link":
                result.append(Link(self, node=node))
        return result

    def get_children(
        self, type: Optional[str] = None  # pylint: disable=redefined-builtin
    ) -> list[str]:
        """Select all children that are directly ours.
        A sorted list of strings (attribute names) is returned.

        It is possible to define a type of children, which can be one of:
          cell, transformer, context, macro, module, foldercell, deepcell,
          or deepfoldercell

        If type is None, all children and descendants are returned:
        - SubContexts are not returned, but their children and descendants are (with full path info)
        - For LibInstance, the children and descendants of the generated SynthContext is returned
        """
        from . import nodeclasses

        classless = ("context", "libinstance")
        all_types = list(classless) + list(nodeclasses.keys())
        assert type is None or type in all_types, (type, all_types)
        children00 = []
        for p, c in self._children.items():
            if isinstance(c, LibInstance) and type != "libinstance":
                for child in c.ctx.get_children():
                    children00.append((child.path, child))
            else:
                children00.append((p, c))
        children0 = children00
        if type is not None and type not in classless:
            klass = nodeclasses[type]
            children0 = [(p, c) for p, c in children00 if isinstance(c, klass)]
        children = [p[0] for p, c in children0]
        if type == "context":
            children = [p for p in children if (p,) not in children00]
        return sorted(list(set(children)))

    @property
    def children(self):
        """Return a wrapper for the direct children of the context.
        This includes subcontexts and libinstances"""
        children = [p[0] for p in self._children]
        g = self._graph[0]
        for k in g:
            if len(k) > 1:
                continue
            node = g[k]
            if node["type"] == "libinstance":
                children.append(k[0])
        children = sorted(list(set(children)))
        return ChildrenWrapper(self, children)

    def __dir__(self):
        d = [p for p in type(self).__dict__ if not p.startswith("_")]
        children = [p[0] for p in self._children]
        children = list(set(children))
        libinstances = []
        g = self._graph[0]
        for k in g:
            if len(k) > 1:
                continue
            node = g[k]
            if node["type"] == "libinstance":
                libinstances.append(k[0])
        return sorted(d + children + libinstances)

    def _destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        self._manager._highlevel_refs -= 1
        if self._gen_context is not None:
            self._gen_context.destroy()
        for lib in self._graph.lib.values():
            checksums = copying.get_checksums(
                lib["graph"]["nodes"],
                lib["graph"]["connections"],
                with_annotations=False,
            )
            for checksum in checksums:
                buffer_cache.decref(bytes.fromhex(checksum))

    def __str__(self):
        p = self.path
        if p == "":
            p = "<toplevel>"
        ret = "Seamless Context: " + p
        return ret

    def __repr__(self):
        return str(self)

    def __copy__(self):
        graph = self.get_graph()
        return Context.from_graph(graph, manager=self._manager)

    def __del__(self):
        self._destroy()


from ..core.manager.tasks.structured_cell import StructuredCellAuthTask
from ..core.manager.tasks import SetCellValueTask, SetCellBufferTask

_auth_task_types = (SetCellValueTask, SetCellBufferTask, StructuredCellAuthTask)

from .Transformer import Transformer
from .Cell import Cell
from .DeepCell import DeepCell, DeepFolderCell
from .Link import Link
from .Macro import Macro
from .Module import Module
from .SelfWrapper import SelfWrapper, ChildrenWrapper
from .pin import PinWrapper
from .library.libinstance import LibInstance
from .PollingObserver import PollingObserver
from .Environment import ContextEnvironment

from ..core.cache.buffer_cache import buffer_cache
from .SubContext import SubContext
from ..core.manager import Manager
from .SeamlessTraitlet import SeamlessTraitlet
from .library import Library
from ..imperative import _cleanup