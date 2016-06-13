import sys, re, os

reservedtypes = (
 "Spyder",
 "Type",
 "Object",
 "Delete",
 "Include",
 "Exception",
 "None",
 "True",
 "False"
)
reserved_membernames = (
  "type","typename","length","name",
  "convert","cast","validate",
  "data","str","repr","dict","fromfile","tofile",
  "listen","block","unblock","buttons","form",
  "invalid",
)


#Regular expressions for:
#    quotes ( "...", '...' )
#    triple quotes ( """...""", '''...''' )
#    curly braces ( {...} )
quotematch = re.compile(r'(([\"\']).*?\2)')
triplequotematch = re.compile(r'(\"\"\"[\w\Wn]*?\"\"\")')
curlymatch = re.compile(r'{[^{}]*?}')

"""
Mask signs to mark out masked-out regions
These mask signs are assumed to be not present in the text
TODO: replace them with rarely-used ASCII codes
       (check that this works with Py3 also)
"""
masksign_triplequote = "&"
masksign_quote = "*"
masksign_curly = "!"


def parse(spytext):
    """
    Converts spytext to a dictionary
     with key = the name of the Spyder type
     and value = the
    """
    ret = {}
    blocks = divide_blocks(spytext)
    print blocks
    for b in blocks:
        print "###"
        print b[:70]
        print "..."
        print b[-70:]
        print "###"
    print len(blocks)
    blocks = blocks[:5]
    for b in blocks:
        blocktype,blockhead,block,blockdocstring = parse_block(b)
        if blocktype is None: continue
        if block is None:
            raise Exception(\
"Non-comment text outside Type definitions is not understood: '%s'" % b
            )
        if blocktype != "Type":
            raise Exception(\
"{}-blocks other than Type are not understood: '%s'" % blocktype
            )

        print "!!!"
        print blocktype
        print blockhead
        print str(block)
        print blockdocstring[:70]
        print "!!!"
    return ret

def divide_blocks(spytext):
    """
    Divides spytext into blocks
    A block is either a curly-brace block structure preceeded by a block type and a block head,
     or it is a single line of text that is outside such a block structure
    Triple-quoted strings outside blocks are automatically removed
    divide_blocks should be invoked
    - first on the entire text,
    - then on the contents of a block                   (Type blocks)
    - then on the contents of a block-inside-a-block    (form blocks, validate blocks, ...)
    """

    #First, take spytext and mask out all triple quote text into s0
    pos = 0
    s0 = ""
    for pp in triplequotematch.finditer(spytext):
        s0 += spytext[pos:pp.start()] + masksign_triplequote * (pp.end()-pp.start())
        pos = pp.end()
    s0 += spytext[pos:]

    #Then, take spytext and mask out all quoted text into mask0
    #To prevent that we also mask out triple quotes, look for quotes only in s0
    p = quotematch.finditer(s0)
    pos = 0
    mask0 = ""
    for pp in p:
        mask0 += spytext[pos:pp.start()] + masksign_quote * (pp.end()-pp.start())
        pos = pp.end()
    mask0 += spytext[pos:]

    #Now, look for curly braces in mask0, and mask them out iteratively (modifying mask0)
    while 1:
        p = curlymatch.finditer(mask0)
        pos = 0
        mask00 = ""
        for pp in p:
            mask00 += mask0[pos:pp.start()] + masksign_curly * (pp.end()-pp.start())
            pos = pp.end()
        mask00 += mask0[pos:]
        if pos == 0: break
        mask0 = mask00

    #Finally, look for triple quote regions in mask00, and mask them out
    pos = 0
    mask = ""
    for pp in triplequotematch.finditer(mask0):
        mask += mask0[pos:pp.start()] + masksign_triplequote  * (pp.end()-pp.start())
        pos = pp.end()
    mask += mask00[pos:]

    #now we split the mask into newlines
    #newlines inside curly blocks will have been masked out
    lines0 = mask.split("\n")
    lines = []
    pos = 0
    for l in lines0:
        pos2 = pos + len(l)
        block = spytext[pos:pos2].strip()
        if len(block):
            lines.append(block)
        pos = pos2 + len("\n")
    return lines

def parse_block(blocktext):
    """
    Parses the content of a block into four parts
    - Block type: the first word
    - Block head: the first line after the block type, before the curly braces
    - Block: content between curly braces (None if no curly braces)
    - Blockdocstring: commented content right after the start of the block
    """
    pos = 0
    s0 = ""
    for pp in triplequotematch.finditer(blocktext):
        s0 += blocktext[pos:pp.start()] + masksign_triplequote * (pp.end()-pp.start())
        pos = pp.end()
    s0 += blocktext[pos:]

    p = quotematch.finditer(s0)
    pos = 0
    mask0 = ""
    for pp in p:
        mask0 += blocktext[pos:pp.start()] + masksign_quote * (pp.end()-pp.start())
        pos = pp.end()
    mask0 += blocktext[pos:]

    preblock = blocktext
    postblock = ""
    blocks = []
    while 1:
        p = curlymatch.finditer(mask0)
        pos = 0
        mask = ""
        blocks0 = []
        for pp in p:
            blocks0.append(blocktext[pp.start():pp.end()])
            preblock = blocktext[pos:pp.start()]
            mask += preblock + masksign_curly * (pp.end()-pp.start())
            pos = pp.end()
        mask += mask0[pos:]
        if pos == 0:
            break
        else:
            postblock = blocktext[pos:]
        blocks = blocks0
        mask0 = mask
    block = None
    if len(blocks) == 1:
        block = blocks[0][1:-1]
    if len(blocks) > 1:
        raise Exception("compile error: invalid statement\n%s\nStatement must contain a single {} block" % blocktext)
        if len(postblock.strip()) != 0:
            raise Exception("compile error: invalid statement\n%s\nStatement must be empty after {} block" % blocktext)
    preblock = preblock.strip()

    blockdocstring = ""

    p = quotematch.finditer(preblock)
    pos = 0
    mask = ""
    for pp in p:
        mask += preblock[pos:pp.start()] + masksign_quote * (pp.end()-pp.start())
        pos = pp.end()
    mask += preblock[pos:]
    comment = mask.find("#")
    if comment > -1:
        blockdocstring = preblock[comment+1:].strip('\n') + '\n'
        preblock = preblock[:comment]

    if block is not None:
        currblock = block
        while 1:
            len0 = len(currblock)
            currblock = currblock.lstrip().lstrip("\n")
            if len(currblock) == len0: break

        pp = triplequotematch.search(currblock)
        if pp is not None and pp.start() == 0:
            blockdocstring += currblock[pp.start()+len('"""'):pp.end()-len('"""')]

    blocktype = None
    blockhead = None
    if len(preblock) > 0:
        blocktype = preblock.split()[0]
        blockhead = preblock[len(blocktype):].strip()

    return blocktype,blockhead,block,blockdocstring
