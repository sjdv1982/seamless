# Import macros
from .optional import macro_optional
from .bracket_length import macro_bracket_length
from .enum import macro_enum


_macros = []


def register_macro(macro):
    _macros.append(macro)


def get_macros():
    return list(_macros)


register_macro(macro_optional)
register_macro(macro_bracket_length)
register_macro(macro_enum)
