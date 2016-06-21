from lxml import etree
from lxml.builder import E
from .. import is_valid_spydertype

def define_error(tree, block):
  from .parse import quotematch
  pq = list(quotematch.finditer(block) )
  currpos = 0
  node = E.errorblock()
  tree.append(node)
  for pnr in range(0, len(pq), 2):
      p1, p2 = pq[pnr], pq[pnr+1]
      mid = block[p1.end():p2.start()].strip().replace("\n","")
      s1, s2 = p1.group(0).strip(), p2.group(0).strip()
      ss1, ss2 = ["\n        " + s[1:-1] +"\n      " for s in s1,s2]
      if mid != "=>":
          raise ValueError("Malformed error statement: \n %s\n    %s\n %s\n'%s' should be '=>'" % (s1,mid, s2,mid))
      node.append(E.error(E.code(ss1), E.message(ss2)))

def typedefblock(tree, name, block):
    from .parse import divide_blocks, parse_block
    assert name in ("optional", "form", "validate", "error"), name
    if name == "error":
        define_error(tree, block)
        return
    elif name == "optional":
        nodename = "optional"
        block = "".join([l.strip() for l in block.splitlines()])
    elif name == "validate":
        nodename = "validationblock"
    elif name == "form":
        nodename = "formblock"
    tree.append( getattr(E, nodename)(block))

def add_doc(last_member, docstring, newdoc):
    if last_member is None:
        docstring.text += newdoc
    else:
        try:
            mdoc = last_member.find("docstring")
        except:
            mdoc = E.docstring(newdoc)
            last_member.append(mdoc)
        mdoc.text += newdoc

def typedefparse(typename, bases, block):
    from .parse import divide_blocks, parse_block, macros
    if not is_valid_spydertype(typename):
        raise Exception("Invalid Spyder type definition: invalid type name: ''%s'" % typename)
    for base in bases:
        if not is_valid_spydertype(base, permit_array=True):
            raise Exception("Invalid Spyder type definition: cannot inherit from non-Spyder type '%s'" % base)
    block_filtered = ""

    methodblock = None
    tree = E.spyder(
      E.typename(typename),
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
    while len(lines) > 0:
        l = lines[0].strip()
        l2 = lines[0].replace('\t', "  ")
        lines = lines[1:]
        if len(l) == 0:
            continue

        if l.startswith("##"):
            l = l[2:].lstrip()
            ll = l.split()
            name = ll[0]
            typedefblock(tree, name, l[len(name)+1:])
            continue
        if l.find("#") == 0:
            continue
        if not inside_def and l.startswith('"""'):
            l = l[3:]
            l = '\n' + l[:l.index('"""')]
            newdoc = l[len('\n'):]
            add_doc(last_member, docstring, newdoc)
            continue
        if inside_def:
            indent = len(l2) - len(l2.lstrip())
            if indent == curr_indent:
                inside_def = False
        if not inside_def:
            if l2.lstrip().startswith("def "):
                curr_indent = len(l2) - len(l2.lstrip())
                inside_def = True
        if inside_def or l2.lstrip().startswith("@"):
            if not inside_methodblock:
                methodblock = E.methodblock("")
                tree.append(methodblock)
                inside_methodblock = True
            methodblock.text += "\n  " + "\n  ".join(l2.split("\n"))
            continue
        else:
            if inside_methodblock:
                methodblock.text += "\n  "
            inside_methodblock = False

        assert not inside_methodblock and not inside_def #bugcheck

        name,title,block,blockcomment = parse_block(l)

        last_member = None
        if block is not None:
            if title != "" and title is not None:
                raise Exception("Malformed block statement, must be <name> {...}\n%s" % (l))
            bb = block.split('\n')
            spaces = -1
            bb2 = []
            for l in bb:
                if len(l.strip()) == 0: continue
                if spaces == -1:
                    spaces = len(l) - len(l.lstrip())
                bb2.append(l.rstrip('\n')[spaces:] )
            block2 = "\n    " + "\n    ".join(bb2) + "\n  "
            typedefblock(tree, name, block2)
        elif len(blockcomment) and not name:
            add_doc(last_member, docstring, blockcomment)
        else:
            if not len(title):
                raise Exception("Malformed %s statement: no title" % (name, l))
            tsplit = title.split()
            if name == "Delete":
                if len(tsplit) != 1:
                    raise Exception("Malformed Delete statement: %s" % l)
                tree.append(E.delete(title))
            elif name in "Include":
                if len(tsplit) != 1:
                    raise Exception("Malformed Include statement: %s" % l)
                tree.append(E.include(title))
            else:
                newlines = None
                for macro in macros:
                    newblock = macro(name, title)
                    if not newblock: continue
                    newlines = divide_blocks(newblock)
                    break
                if newlines is not None:
                    lines[:] = newlines + lines
                    continue
                init = None
                if len(tsplit) > 1:
                    if tsplit[1] != "=":
                        raise Exception("Malformed member statement: %s" % l)
                    title = tsplit[0]
                    init = " ".join(tsplit[2:])
                if not is_valid_spydertype(name, permit_array=True):
                    raise TypeError("Invalid member name '%s'" % name)
                member = E.member(E.name(title),E.type(name))
                if init is not None:
                    member.append(E.init(init))
                tree.append(member)
                last_member = member
    if inside_methodblock:
        methodblock.text += "\n  "
    return tree
