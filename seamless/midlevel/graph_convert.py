"""Converts various ancient graph formats into modern format
"""

from copy import deepcopy
import json
import warnings

def graph_convert_pre07(graph, ctx):
    from ..core.cache import CacheMissError
    from ..core.cache.buffer_cache import buffer_cache
    graph = deepcopy(graph)
    graph["__seamless__"] = "0.7"
    def get_buffer(checksum):
        if ctx is not None:
            try:
                buf = ctx.resolve(checksum)
            except CacheMissError:
                buf = None
        else:
            buf = buffer_cache.get_buffer(bytes.fromhex(checksum))
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
            if node.get("hash_pattern") != {'*': '#'}:
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
                print("Warning: ignoring docker_options from antique Docker transformer")
                auth.pop("docker_options")
            if "docker_image" in auth:
                docker_image_checksum = auth.pop("docker_image")
                docker_image = get_buffer(docker_image_checksum)
                if docker_image is None:                
                    raise CacheMissError(msg.format(path, docker_image_checksum))
                docker_image = json.loads(docker_image)
                if "environment" not in node:
                    node["environment"] = {}
                node["environment"]["image"] = {
                    "name": docker_image 
                }
    connections_to_remove = []
    for cnr, connection in enumerate(graph["connections"]):
        if connection["type"] == "connection":
            path = tuple(connection["target"])
            if path[-1] in ("docker_image", "docker_options"):
                if path[:-1] in converted_nodes:
                    warnings.warn("Removed connection: {}".format(connection))
                    connections_to_remove.append(cnr)
    graph["connections"][:] = [c for cnr,c in enumerate(graph["connections"]) if cnr not in connections_to_remove]
    return graph


def graph_convert(graph, ctx):
    if ctx is not None:
        from ..highlevel.Context import Context
        assert isinstance(ctx, Context)
    if not isinstance(graph, dict):
        raise TypeError(type(graph))
    seamless_version = graph.get("__seamless__")
    if seamless_version is None: #pre-0.7
        graph = graph_convert_pre07(graph, ctx)
    return graph