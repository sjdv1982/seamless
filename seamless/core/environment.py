import conda
from conda.models.match_spec import MatchSpec
from conda.cli.python_api import Commands, run_command as conda_run

async def validate_conda_environment(environment):
    condenv = environment.get("conda")
    if condenv is None:
        return False
    for dep in condenv.get("dependencies", []):
        ms = MatchSpec(dep)
        info = conda_run(Commands.LIST, ["-f", ms.name])[0]
        for l in info.split("\n"):
            l = l.strip()
            if l.startswith("#"):
                continue
            ll = l.split()
            if len(ll) < 2:
                continue
            if ll[0] != ms.name:
                continue
            if ms.version.match(ll[1]):                
                break
            else:
                # TODO: record incompatible version
                pass
        else:
            return False
    return True
        
    

async def validate_environment(environment):
    if await validate_conda_environment(environment):
        return
    ### TODO
    raise ValueError("Incompatible environment")  # TODO: error message