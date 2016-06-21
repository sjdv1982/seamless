# Copyright 2007-2016, Sjoerd de Vries

from . import register_macro


def macro_optarg(name, content):
    if name[0] != "*":
        return

    original_content = content
    for i, char in enumerate(content):
        if char.isalnum() == False and char != "_":
            content = char
            break

    return name[1:] + " " + original_content + "\noptional {\n  " + content + "\n}\n"


register_macro(macro_optarg)
