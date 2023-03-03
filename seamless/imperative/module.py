from types import ModuleType
import inspect

def get_module_definition(module:ModuleType) -> dict[str]:
    from ..core.build_module import module_definition_cache
    if module in module_definition_cache:
        result = module_definition_cache[module]
    else:
        # TODO: use /home/sjoerd/seamless/seamless/highlevel/stdlib/map/build.py:bootstrap
        code = inspect.getsource(module).strip("\n")
        result = {
            "code": code,
            "language": "python",
            "type": "interpreted"
        }
    return result
