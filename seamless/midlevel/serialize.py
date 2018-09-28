from copy import deepcopy

transformer_states = (
    ("input", "stored_state_input", True),
    ("input", "cached_state_input", False),
    ("result", "cached_state_result", False),
)

transformer_values = (
    ("code", "code", True),
    ("code", "cached_code", False),
)

reactor_states = (
    ("io", "stored_state_io", True),
    ("io", "cached_state_io", False),
)

reactor_values = (
    ("code_start", "code_start", True),
    ("code_start", "cached_code_start", False),
    ("code_update", "code_update", True),
    ("code_update", "cached_code_update", False),
    ("code_stop", "code_stop", True),
    ("code_stop", "cached_code_stop", False),
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
            for sub, key, is_not_cached in transformer_states:
                state = result.pop(key, None)
                if state is not None:
                    mstates = states if is_not_cached else cached_states
                    mstates[path+"."+sub] = state.serialize()
            for sub, key, is_not_cached in transformer_values:
                value = result.pop(key, None)
                if value is not None:
                    mvalues = values if is_not_cached else cached_values
                    mvalues[path+"."+sub] = value

        elif nodetype == "reactor":
            for sub, key, is_not_cached in reactor_states:
                state = result.pop(key, None)
                if state is not None:
                    mstates = states if is_not_cached else cached_states
                    mstates[path+"."+sub] = state.serialize()
            for sub, key, is_not_cached in reactor_values:
                value = result.pop(key, None)
                if value is not None:
                    mvalues = values if is_not_cached else cached_values
                    mvalues[path+"."+sub] = value
        elif nodetype == "connection":
            pass
        elif nodetype == "context":
            pass
        elif nodetype == "link":
            pass
        else:
            raise TypeError(nodetype)
        topology.append(result)
    topology += connections
    return topology, values, states, cached_values, cached_states
