from ..silk.typeparse.parse import mask_characters
from .parse_slash0_funcs import cmd_funcs, firstpass
from .parse_slash0_utils import syntax_error, tokenize, \
    double_quote, single_quote, quote_match

import re

def parse_slash0(code):
    exports = []
    commands = []
    nodes = dict(
        env = [],
        file=[],
        doc=[],
        variable=[],
        context=[],
    )
    if code.find('"""') > -1 or code.find("'''") > -1:
        raise SyntaxError("Triple quotes not supported")
    lines = []
    for lnr, l in enumerate(code.splitlines()):
        while 1:
            l = l.strip()
            if not len(l):
                break
            if l.endswith("\\"):
                syntax_error(lnr+1, l, "Line continuations not supported")
            lmask = mask_characters(quote_match, l, l, '*')[0]
            find_comment = lmask.find("#")
            if find_comment > -1:
                l = l[:find_comment]
            else:
                break
        if not len(l):
            continue

        if len(list(double_quote.finditer(lmask))):
            syntax_error(lnr+1, l, 'Unmatched " (double quote)')
        if len(list(single_quote.finditer(lmask))):
            syntax_error(lnr+1, l, "Unmatched ' (single quote)")
        pos = 0
        assign = lmask.find("=")
        words = tokenize(l, lmask)
        source = " ".join(words)
        if assign > -1:
            lines.append(("assign", lnr, source, words))
            continue
        command = words[0]
        if command.startswith("@"):
            command = command[1:]
            if command in ("assign", "standard") or command not in cmd_funcs:
                syntax_error(lnr+1, l, "Unknown command: {0}".format(command))
            lines.append((command, lnr, source, words))
        else:
            lines.append(("standard", lnr, source, words))

    #First pass (declarations)
    for line in lines:
        command_name = line[0]
        if command_name not in firstpass:
            continue
        cmd_funcs[command_name](line, nodes)

    #exports
    for line in lines:
        command_name = line[0]
        if command_name != "export":
            continue
        export = cmd_funcs[command_name](line, nodes)
        exports.append(export)

    #Second pass (commands)
    for line in lines:
        command_name = line[0]
        if command_name in firstpass:
            continue
        if command_name == "export":
            continue
        cmd = cmd_funcs[command_name](len(commands)+1, line, nodes)
        commands.append(cmd)

    result = {
        "nodes": nodes,
        "commands": commands,
        "exports": exports
    }
    return result
