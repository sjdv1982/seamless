_macros = []
def register_macro(macro):
    _macros.append(macro)

def get_macros():
    return list(_macros)

from . import optarg, bracketlength, enum
