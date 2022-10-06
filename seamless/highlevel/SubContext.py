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

"""SubContext class that helps to organize cells and workers hierarchically."""

from __future__ import annotations
from typing import *
import inspect
from copy import deepcopy

from seamless.core.context import StatusReport
from .Base import Base
from .HelpMixin import HelpMixin
from .assign import assign
from .proxy import Pull


class SubContext(Base, HelpMixin):
    """Wraps a portion of a workflow graph.
    Is always part of a parent Context.

    The portion is defined as all children whose path
    starts with a certain path tuple.
    E.g. ("spam", "eggs") would contain Cell ("spam", "eggs", "ham")
    and Transformer ("spam", "eggs", "ni").
    The SubContext would be available as ctx.spam.eggs,
    and the children as ctx.spam.eggs.ham and ctx.spam.eggs.ni.

    Typical usage:

    A SubContext is never directly instantiated by the user.
    It is created by assigning a Context to another Context.
    For example, given a Context `ctx2` with child Cells `a` and `b`,
    `ctx.sub = ctx2` will create SubContext `ctx.sub`, and add child Cells
    ctx.sub.a` and `ctx.sub.b`.
    """

    def __getitem__(self, attr: str) -> Base:
        if not isinstance(attr, str):
            raise KeyError(attr)
        return getattr(self, attr)

    def __setitem__(self, attr: str, value: Any):
        if not isinstance(attr, str):
            raise KeyError(attr)
        setattr(self, attr, value)

    def __getattribute__(self, attr: str):
        if attr.startswith("_"):
            return super().__getattribute__(attr)
        if hasattr(type(self), attr) or attr in self.__dict__ or attr == "path":
            return super().__getattribute__(attr)
        parent = self._get_top_parent()
        assert self._path is not None
        path: tuple[str, ...] = self._path + (attr,)
        return parent._get_from_path(path)

    def __setattr__(self, attr: str, value: Any):
        if attr.startswith("_"):
            return object.__setattr__(self, attr, value)
        members = {k: v for k, v in inspect.getmembers(type(self))}
        if attr in members and isinstance(members[attr], property):
            return object.__setattr__(self, attr, value)
        parent = self._get_top_parent()
        assert self._path is not None
        path: tuple[str, ...] = self._path + (attr,)
        if isinstance(value, Transformer):
            if value._parent is None:
                parent._graph[0][path] = value
                value._init(parent, path)
                parent._translate()
            else:
                assign(parent, path, value)
        elif isinstance(value, Pull):
            value._proxy._pull_source(path)
        else:
            assign(parent, path, value)

    def __delattr__(self, attr):
        if attr.startswith("_"):
            return super().__delattr__(attr)
        parent = self._get_top_parent()
        path = self._path + (attr,)
        parent._destroy_path(path)

    def _get_graph_dict(self, copy: bool, runtime: bool = False) -> dict[str, Any]:
        """See .get_graph"""
        parent = self._get_parent()
        parent._wait_for_auth_tasks("the graph is being obtained")
        nodes, connections, params, _ = parent._graph
        path = self._path
        assert path is not None
        pathl = list(path)
        lp = len(path)
        newnodes = []
        for nodepath, node in sorted(nodes.items(), key=lambda kv: kv[0]):
            if len(nodepath) > lp and nodepath[:lp] == path:
                newnode = deepcopy(node)
                if newnode["type"] == "libinstance":
                    nodelib = parent._graph.lib[tuple(newnode["libpath"])]
                    for argname, arg in list(newnode["arguments"].items()):
                        param = nodelib["params"][argname]
                        if param["type"] in ("cell", "context"):
                            if isinstance(arg, tuple):
                                arg = list(arg)
                            if not isinstance(arg, list):
                                arg = [arg]
                            if len(arg) > lp and arg[:lp] == pathl:
                                arg = arg[lp:]
                        elif param["type"] == "celldict":
                            for _, v in arg.items():
                                if isinstance(v, tuple):
                                    v = list(v)
                                if not isinstance(v, list):
                                    v = [v]
                                if len(v) > lp and v[:lp] == pathl:
                                    v = v[lp:]
                        newnode["arguments"][argname] = arg
                newnode["path"] = nodepath[lp:]
                newnodes.append(newnode)
        new_connections = []
        for connection in connections:
            if connection["type"] == "connection":
                source, target = connection["source"], connection["target"]
                if source[:lp] == path and target[:lp] == path:
                    con = deepcopy(connection)
                    con["source"] = source[lp:]
                    con["target"] = target[lp:]
                    new_connections.append(con)
            elif connection["type"] == "link":
                first, second = connection["first"], connection["second"]
                if first[:lp] == path and second[:lp] == path:
                    con = deepcopy(connection)
                    con["first"] = first[lp:]
                    con["second"] = second[lp:]
                    new_connections.append(con)
        if copy:
            params = deepcopy(params)
        graph = {
            "nodes": newnodes,
            "connections": new_connections,
            "params": params,
            "lib": {},
        }
        return graph

    def get_graph(self, runtime: bool = False) -> dict[str, Any]:
        """Obtain our portion of the parent context's graph
        In essence, take the parent graph, select all child nodes that
        start with our path, and chop off that path.
        Retain connections between two child nodes that are in our graph.
        """
        graph = self._get_graph_dict(copy=True, runtime=runtime)
        return graph

    @property
    def status(self) -> StatusReport | str:
        """Get the status of our children.

        Essentially, this does the same as Context.status,
        selecting only the children that are ours (start with self._path).

        Returns a StatusReport with the .status of each child that is doesn't have status OK.
        If there are no such children, return "Status: OK".
        """
        parent = self._get_parent()
        nodes, _, _, _ = parent._graph
        return _get_status(parent, parent._children, nodes, self._get_path())

    def _translate(self):
        self._get_parent()._translate()

    def get_children(self, type: Optional[str] = None) -> list[str]:
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
        if not (type is None or type in classless or type in nodeclasses):
            raise TypeError(
                "Unknown type {}, must be in {}".format(type, nodeclasses.keys())
            )
        l = len(self._get_path())
        children00 = [
            (p[l:], c)
            for p, c in self._get_parent()._children.items()
            if len(p) > l and p[:l] == self._path
        ]
        children0 = children00
        if type is not None and type not in classless:
            klass = nodeclasses[type]
            children0 = [(p, c) for p, c in children00 if isinstance(c, klass)]
        children = [p[0] for p, c in children0]
        if type == "context":
            children = [p for p in children if (p,) not in children00]
        return sorted(list(set(children)))

    @property
    def children(self) -> dict[str, Base]:
        """Returns a wrapper for the direct children of the context
        This includes subcontexts and libinstances"""
        result = {}
        parent = self._get_top_parent()
        for k in self.get_children(type=None):
            path = self._get_path() + (k,)
            child = parent._get_from_path(path)
            result[k] = child
        return result

    def __str__(self):
        ret = "Seamless SubContext: " + self.path
        return ret

    def __repr__(self):
        return str(self)

    def __dir__(self):
        d = [p for p in type(self).__dict__ if not p.startswith("_")]
        return sorted(d + self.get_children())


from .Context import _get_status
from .Transformer import Transformer
