from copy import deepcopy

transformer_states = (
    ("input", "stored_state_input", True),
    ("input", "cached_state_input", False),
    ("result", "cached_state_result", False),
)


def extract(nodes, connections):
    topology = []
    values = {}
    cached_values = {}
    states = {}
    cached_states = {}
    for path0, node in nodes.items():
        path = ".".join(path0)
        nodetype = node["type"]
        result = deepcopy(node)
        if nodetype == "cell":
            value = result.pop("stored_value", None)
            if value is not None:
                values[path] = value
            cached_value = result.pop("cached_value", None)
            if cached_value is not None:
                cached_values[path] = cached_value
            state = result.pop("stored_state", None)
            if state is not None:
                states[path] = state.serialize()
            cached_state = result.pop("cached_state", None)
            if cached_state is not None:
                cached_states[path] = cached_state.serialize()
        elif nodetype == "transformer":
            for sub, key, is_stored in transformer_states:
                state = result.pop(key, None)
                if state is not None:
                    states = states if is_stored else cached_states
                    states[path+"."+sub] = state.serialize()
        topology.append(result)
    topology += connections
    return topology, values, states, cached_values, cached_states
