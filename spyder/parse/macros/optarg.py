# Copyright 2007-2016, Sjoerd de Vries

from . import register_macro

def macro_optarg(name, content):
    if name[0] != "*": return
    content0 = content
    for n in range(len(content)):
        if content[n].isalnum() == False and content[n] != "_":
            content = content[:n]
            break
    ret = name[1:] + " " + content0 + "\noptional {\n  " + content + "\n}\n"
    return ret

register_macro(macro_optarg)
