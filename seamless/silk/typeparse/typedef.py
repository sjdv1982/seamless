from lxml.builder import E

from ..exceptions import SilkSyntaxError
from ..validate import is_valid_silktype


def define_error(tree, block):
    from .parse import single_quote_match
    matches = single_quote_match.finditer(block)
    node = E.errorblock()
    tree.append(node)

    for p1, p2 in zip(matches, matches):
        mid = block[p1.end():p2.start()].strip().replace("\n", "")

        s1 = p1.group(0).strip()
        s2 = p2.group(0).strip()

        ss1, ss2 = ["\n        " + s[1:-1] + "\n      " for s in (s1, s2)]

        if mid != "=>":
            raise ValueError("Malformed error statement: \n %s\n    %s\n %s\n'%s' should be '=>'" % (s1, mid, s2, mid))

        node.append(E.error(E.code(ss1), E.message(ss2)))

def typedef_memberblock(tree, name, block):
    if name == "optional":
        node_name = "optional"
        block = "1"
        is_attr = True
    elif name == "enum":
        node_name = "enum"
        block = "".join([l.strip() for l in block.splitlines()])
        is_attr = False
    else:
        return None
    return node_name, block, is_attr

def typedef_block(tree, name, block):
    if name == "error":
        define_error(tree, block)
        return

    elif name == "validate":
        node_name = "validationblock"

    elif name == "form":
        node_name = "formblock"

    else:
        raise ValueError(name)

    tree.append(getattr(E, node_name)(block))


def add_doc(last_member, docstring, new_docstring):
    if last_member is None:
        docstring.text += new_docstring

    else:
        try:
            element = last_member.find("docstring")

        except Exception:
            element = E.docstring(new_docstring)
            last_member.append(element)

        element.text += new_docstring


def typedef_parse(typename, bases, block):
    from .parse import divide_blocks, parse_block
    from .macros import get_macros

    macros = get_macros()

    if not is_valid_silktype(typename):
        raise SilkSyntaxError("Invalid silk type definition: invalid type name: ''%s'" % typename)

    for base in bases:
        if not is_valid_silktype(base, permit_array=True):
            raise SilkSyntaxError("Invalid silk type definition: cannot inherit from non-silk type '%s'" % base)

    methodblock = None
    tree = E.silk(
      typename=typename,
    )
    for base in bases:
        tree.append(E.base(base))

    docstring = E.docstring("")
    tree.append(docstring)
    lines = divide_blocks(block)
    inside_def = False
    inside_methodblock = False
    curr_indent = 0
    last_member = None

    while lines:
        line = lines[0].strip()
        line_tabs_as_spaces = lines[0].replace('\t', "  ")
        lines = lines[1:]

        if not line:
            continue

        if line.startswith("##"):
            line = line[2:].lstrip()
            if len(line.split()) < 2:
                raise SilkSyntaxError(line)
            name = line.split()[0]
            typedef_block(tree, name, line[len(name) + 1:])
            continue

        if line.find("#") == 0:
            continue

        if not inside_def and line.startswith('"""'):
            line = line[3:]
            end_quotes_index = line.index('"""')
            between_quotes = line[:end_quotes_index]
            add_doc(last_member, docstring, between_quotes)
            continue

        if inside_def:
            indent = len(line_tabs_as_spaces) - len(line_tabs_as_spaces.lstrip())
            if indent == curr_indent:
                inside_def = False

        if not inside_def:
            if line_tabs_as_spaces.lstrip().startswith("def "):
                curr_indent = len(line_tabs_as_spaces) - len(line_tabs_as_spaces.lstrip())
                inside_def = True

        if inside_def or line_tabs_as_spaces.lstrip().startswith("@"):
            if not inside_methodblock:
                methodblock = E.methodblock("")
                tree.append(methodblock)
                inside_methodblock = True

            methodblock.text += "\n  " + "\n  ".join(line_tabs_as_spaces.split("\n"))
            continue

        else:
            if inside_methodblock:
                methodblock.text += "\n  "
            inside_methodblock = False

        assert not inside_methodblock and not inside_def #bugcheck

        name, title, block, block_comment = parse_block(line)

        if block is not None:
            if title != "" and title is not None:
                raise SilkSyntaxError("Malformed block statement, must be <name> {...}\n%s" % (line))

            spaces = None

            block_lines = block.split('\n')
            reformatted_block_lines = []

            for line in block_lines:
                if not line.strip():
                    continue

                # Find indentation
                if spaces is None:
                    spaces = len(line) - len(line.lstrip())

                reformatted_block_lines.append(line.rstrip('\n')[spaces:])
            reformatted_block = "\n    " + "\n    ".join(reformatted_block_lines) + "\n  "

            memberblock = None
            if last_member is not None:
                memberblock = typedef_memberblock(tree, name, reformatted_block)
                if memberblock is not None:
                    if memberblock[2]:
                        last_member.attrib[memberblock[0]] = memberblock[1]
                    else:
                        last_member.append(getattr(E, memberblock[0])(memberblock[1]))
            if memberblock is None:
                typedef_block(tree, name, reformatted_block)
                last_member = None

        elif block_comment and not name:
            add_doc(last_member, docstring, block_comment)

        else:
            if not title:
                raise SilkSyntaxError("Malformed %s statement: NOT_REQUIRED title" % (name, line))

            split_title = title.split()

            if name == "Delete":
                if len(split_title) != 1:
                    raise SilkSyntaxError("Malformed Delete statement: %s" % line)

                tree.append(E.delete(title))

            elif name in "Include":
                if len(split_title) != 1:
                    raise SilkSyntaxError("Malformed Include statement: %s" % line)
                tree.append(E.include(title))

            else:
                newlines = None
                for macro in macros:
                    new_block = macro(name, title)
                    if not new_block:
                        continue

                    newlines = divide_blocks(new_block)
                    break

                if newlines is not None:
                    lines[:] = newlines + lines
                    continue

                init_statement = None
                if len(split_title) > 1:
                    if split_title[1] != "=":
                        raise SilkSyntaxError("Malformed member statement: %s" % line)

                    title = split_title[0]
                    init_statement = " ".join(split_title[2:])

                if not is_valid_silktype(name, permit_array=True):
                    raise TypeError("Invalid member name '%s'" % name)

                member = E.member(E.name(title), E.type(name))
                if init_statement is not None:
                    member.append(E.init(init_statement))

                tree.append(member)
                last_member = member

    if inside_methodblock:
        methodblock.text += "\n  "

    if not len(docstring.text):
        tree.remove(docstring)
    return tree
