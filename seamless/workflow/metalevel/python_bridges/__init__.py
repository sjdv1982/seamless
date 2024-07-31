# To install another language:
# - update default_bridges below
# - update languages.cson in seamless/compiler

from ...highlevel.Environment import ContextEnvironment, Environment

from . import r

_default_bridges = {
    "r": {
        "code": r.bridge_r,
        "params": r.default_bridge_parameters,
        "environment": {
            "which": ["R", "Rscript"],
            "conda": """
            dependencies:
            - rpy2
            """,            
        }
    }
}

def load_py_bridges(env: ContextEnvironment):
    for lang in _default_bridges:
        b = _default_bridges[lang]
        if env._py_bridges is None:
            env._py_bridges = {}
        env.set_py_bridge(lang, b["code"])
        params = b.get("params")
        if params is not None:
            env.set_py_bridge_parameters(lang, params)
        if "environment" in b:
            e = b["environment"]
            bridge_env = Environment()
            if "conda" in e:
                bridge_env.set_conda(e["conda"], format="yaml")
            if "which" in e:
                bridge_env.set_which(e["which"], format="plain")
        env.set_py_bridge_environment(lang, bridge_env)
