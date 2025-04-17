"""Converts various ancient graph formats into modern format"""

from copy import deepcopy
import json
import warnings

from seamless import Checksum, CacheMissError
from seamless.checksum.buffer_cache import buffer_cache


def graph_convert_pre07(graph, ctx):

    graph = deepcopy(graph)
    graph["__seamless__"] = "0.8"

    def get_buffer(checksum: Checksum):
        checksum = Checksum(checksum)
        if ctx is not None:
            try:
                buf = ctx.resolve(checksum)
            except CacheMissError:
                buf = None
        else:
            buf = buffer_cache.get_buffer(checksum, remote=True)
        return buf

    converted_nodes = set()
    for node in graph["nodes"]:
        if node["type"] == "transformer" and node["language"] == "docker":
            node["language"] = "bash"
            converted_nodes.add(tuple(node["path"]))
            node["pins"].pop("docker_image", None)
            node["pins"].pop("docker_options", None)
            if "checksum" not in node:
                continue
            path = "." + ".".join(node["path"])
            auth_checksum = node["checksum"].get("input_auth")
            if auth_checksum is None:
                continue
            if node.get("hash_pattern") != {"*": "#"}:
                raise ValueError("Graph contains antique non-deep Docker transformers")

            msg = "Antique Docker transformer: {}, checksum: {}"
            auth_buf = get_buffer(auth_checksum)
            if auth_buf is None:
                raise CacheMissError(msg.format(path, auth_checksum))
            auth = json.loads(auth_buf)
            if not isinstance(auth, dict):
                raise TypeError(msg.format(path, auth_checksum))
            if "docker_image" not in auth and "docker_options" not in auth:
                continue
            if "docker_options" in auth:
                for k in list(node["checksum"].keys()):
                    if k.startswith("input"):
                        node["checksum"].pop(k)
                print(
                    "Warning: ignoring docker_options from antique Docker transformer"
                )
                auth.pop("docker_options")
            if "docker_image" in auth:
                docker_image_checksum = auth.pop("docker_image")
                docker_image = get_buffer(docker_image_checksum)
                if docker_image is None:
                    raise CacheMissError(msg.format(path, docker_image_checksum))
                docker_image = json.loads(docker_image)
                if "environment" not in node:
                    node["environment"] = {}
                node["environment"]["docker"] = {"name": docker_image}
    connections_to_remove = []
    for cnr, connection in enumerate(graph["connections"]):
        if connection["type"] == "connection":
            path = tuple(connection["target"])
            if path[-1] in ("docker_image", "docker_options"):
                if path[:-1] in converted_nodes:
                    warnings.warn("Removed connection: {}".format(connection))
                    connections_to_remove.append(cnr)
    graph["connections"][:] = [
        c
        for cnr, c in enumerate(graph["connections"])
        if cnr not in connections_to_remove
    ]
    return graph


def graph_convert_07(graph, ctx):
    graph = deepcopy(graph)
    graph["__seamless__"] = "0.8"

    for node in graph["nodes"]:
        if node["type"] == "cell" and node.get("mount", {}).get("as_directory"):
            has_incoming_connections = False
            has_outgoing_connections = False
            path = node["path"]
            for connection in graph["connections"]:
                if connection["type"] != "connection":
                    continue
                source = tuple(connection["source"])
                target = tuple(connection["target"])
                if source[:-1] == path or source == path:
                    has_outgoing_connections = True
                if target[:-1] == path or target == path:
                    has_incoming_connections = True

            mount = node["mount"]
            mount.pop("as_directory")
            msg = ""
            if mount.get("mode") == "rw":
                if has_incoming_connections:
                    msg = "Mount mode set to 'w'."
                    mount["mode"] = "w"
                    if has_outgoing_connections:
                        msg += "\nOutgoing connections broken."
                        graph["connections"][:] = [
                            c
                            for c in graph["connections"]
                            if c["source"] != path and c["source"][:-1] != path
                        ]
                else:
                    msg = "Mount mode set to 'r'."
                    mount["mode"] = "r"

            print(
                """WARNING: converting Seamless 0.7 graph.
Directory-mounted plain Cells are converted to FolderCells.

Note that the stored value checksum has been deleted.
The value will be re-read from the mounted directory.

{}""".format(
                    msg
                )
            )
            checksum = node.get("checksum", {})
            checksum.pop("value", None)
            if not checksum:
                node.pop("checksum", None)
            node["type"] = "foldercell"
            node.pop("celltype")
            mount["directory_text_only"] = True
    return graph


def graph_convert_011(graph):
    graph = deepcopy(graph)
    graph["__seamless__"] = "0.11"
    for node in graph["nodes"]:
        if node["type"] == "transformer":
            for _, pin in node.get("pins", {}).items():
                subcelltype = pin.pop("subcelltype", None)
                if subcelltype is None:
                    continue
                celltype = pin.get("celltype")
                if subcelltype != "module" or celltype != "plain":
                    print(
                        """WARNING: legacy subcelltype that is not 'module', ignoring:
Transformer: {}""".format(
                            "." + ".".join(node.get("path", []))
                        )
                    )
                pin["celltype"] = "module"
    return graph


def graph_convert(graph, ctx):
    if ctx is not None:
        from ..highlevel.Context import Context

        assert isinstance(ctx, Context)
    if not isinstance(graph, dict):
        raise TypeError(type(graph))
    seamless_version = graph.get("__seamless__")
    if seamless_version is None:  # pre-0.7
        graph = graph_convert_pre07(graph, ctx)
    elif seamless_version == "0.7":
        graph = graph_convert_07(graph, ctx)
    if seamless_version == "0.8":
        graph = graph_convert_011(graph)
    return graph
