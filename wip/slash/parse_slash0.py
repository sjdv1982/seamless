from seamless.silk.typeparse.parse import mask_characters
from parse_slash0_funcs import cmd_funcs, firstpass
from parse_slash0_utils import tokenize, double_quote, single_quote

from collections import OrderedDict
import re
quote_match = re.compile(r'(([\"\']).*?\2)')

def syntax_error(lineno, line, message):
    msg = """Line {0}:
    {1}
Error message:
    {2}""".format(lineno+1, line, message)
    raise SyntaxError(msg)

def parse_slash0(code):
    nodes = OrderedDict(
        env = [],
        file=[],
        cell=[],
        variable=[],
        context=[],
    )
    if code.find('"""') > -1 or code.find("'''") > -1:
        raise SyntaxError("Triple quotes not supported")
    lines = []
    for lnr, l in enumerate(code.splitlines()):
        l = l.strip()
        if not len(l):
            continue
        if l.endswith("\\"):
            syntax_error(lnr, l, "Line continuations not supported")
        lmask, mask_matches = mask_characters(quote_match, l, l, '*')
        maskpos = [(match.start(), match.end()) for match in mask_matches]
        if len(list(double_quote.finditer(lmask))):
            syntax_error(lnr, l, 'Unmatched " (double quote)')
        if len(list(single_quote.finditer(lmask))):
            syntax_error(lnr, l, "Unmatched ' (single quote)")
        pos = 0
        assign = lmask.find("=")
        words = tokenize(l, lmask)
        if assign > -1:
            lines.append(("assign", lnr, l, words))
            continue
        command = words[0]
        if command.startswith("@"):
            command = command[1:]
            if command in ("assign", "standard") or command not in cmd_funcs:
                syntax_error(lnr, l, "Unknown command: {0}".format(command))
            lines.append((command, lnr, l, words))
        else:
            lines.append(("standard", lnr, l, words))
    for line in lines:
        print(line)

    for line in lines:
        command = line[0]
        if command not in firstpass:
            continue
        cmd_funcs[command](line, nodes)

if __name__ == "__main__":
    example = """
    @input_cell pdb
    @intern_json pdbsplit
    @cell pdb
    $ATTRACTTOOLS/splitmodel !pdb "model">NULL !> pdbsplit
    @export pdbsplit
    """
    tree = parse_slash0(example)
