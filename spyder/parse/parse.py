# Copyright 2007-2016, Sjoerd de Vries

import sys, re, os
from collections import namedtuple

from .macros import get_macros
from .typedef import typedef_parse
from ..exceptions import SpyderParseError

from tokenize import generate_tokens

# from ..validate import is_valid_spydertype

# Regular expressions
# quotes ( "...", '...' )
# triple quotes ( """...""", '''...''' )
# curly braces ( {...} )
single_quote_match = re.compile(r'(([\"\']).*?\2)')
triple_quote_match = re.compile(r'(\"\"\"[\w\Wn]*?\"\"\")')
curly_brace_match = re.compile(r'{[^{}]*?}')


"""
Mask signs to mark out masked-out regions
These mask signs are assumed to be not present in the text
TODO: replace them with rarely-used ASCII codes
       (check that this works with Py3 also)
"""
mask_sign_triple_quote = "&"
mask_sign_single_quote = "*"
mask_sign_curly = "!"

BlockParseResult = namedtuple("BlockParseResult", "block_type block_head block block_docstring")


class Token:

    def __init__(self, character=None):
        self.character = character

    def __repr__(self):
        return "{}({})".format(self.__class__.__name__, self.character)


class Word(Token):
    pass


class BlockStart(Token):
    pass


class BlockEnd(Token):
    pass


class StringType:
    NONE, MULTI, SINGLE = range(3)


def _split_blocks(string):
    block_depth = 0
    for char in string:
        if char == '{':
            block_depth += 1

        elif char == '}':
            block_depth -= 1


def _tokenize_first_pass(string):
    tokens = []

    is_escaped = False
    in_string = False

    stack = []

    current_string = []
    current_string_char = None

    for char in string:
        if char == '"':
            in_string = True

            if stack[-1] == 1:pass

        if char == '{':
            tokens.append()

        stack.append(char)



def tokenise(string):
    tokens = []

    for char in string:
        if char in {'{', '}'}:
            tokens.append()


def parse(spytext):
    """Converts spytext to a dictionary  with key (the name of the Spyder type) -> value (the lxml tree)"""
    result = {}
    blocks = divide_blocks(spytext)
    for block in blocks:
        block_type, block_head, block, block_docstring_dummy = parse_block(block)

        if block_type is None:
            continue

        if block is None:
            raise SpyderParseError("Non-comment text outside Type definitions is not understood: '%s'" % block)

        if block_type != "Type":
            raise SpyderParseError("Top-level {}-blocks other than Type are not understood: '%s'" % block_type)

        block_head_words = block_head.split(":")
        if len(block_head_words) > 2:
            raise SpyderParseError("Type header '%s' can contain only one ':'" % block_head)

        typename = block_head_words[0]
        bases = []

        if len(block_head_words) == 2:
            bases = [b.strip() for b in block_head_words[1].split(",")]

        result[typename] = typedef_parse(typename, bases, block)

    return result


def mask_characters(expression, search_text, target_text, mask_char):
    """Mask characters found by a regular expression with mask character. Mask characters will equal length of masked
    string.
    A different target text to search text may be used, but the developer must ensure that they are compatible.
    This feature may be used to handle combinations of N mask_char(s) differently

    :param expression: regex expression
    :param search_text: text to search for matches
    :param target_text: text to apply mask to
    :param mask_char: character to replace masked characters
    """
    pos = 0
    masked_text = ""
    for match in expression.finditer(search_text):
        masked_text += target_text[pos:match.start()] + mask_char * (match.end() - match.start())
        print(masked_text)
        pos = match.end()

    masked_text += target_text[pos:]
    return masked_text, pos


def divide_blocks(spytext):
    """Divides spytext into blocks.

    A block is either a curly-brace block structure preceeded by a block type and a block head, or it is a single
    line of text that is outside such a block structure.

    Triple-quoted strings outside blocks are automatically removed.

    Divide_blocks should be invoked
    - first on the entire text,
    - then on the contents of a block                   (Type blocks)
    - then on the contents of a block-inside-a-block    (form blocks, validate blocks, ...)
    """

    # First, take spytext and mask out all triple quote text into s0
    masked_triple_quote, _ = mask_characters(triple_quote_match, spytext, spytext, mask_sign_triple_quote)
    # Then, take spytext and mask out all quoted text into masked_single_quote
    # To prevent that we also mask out triple quotes, look for quotes only in masked_triple_quote
    masked_single_quote, _ = mask_characters(single_quote_match, masked_triple_quote, spytext, mask_sign_single_quote)
    # Now, look for curly braces in masked_single_quote, and mask them out iteratively (modifying masked_single_quote)
    while True:
        masked_curly_brace, pos = mask_characters(curly_brace_match, masked_single_quote, masked_single_quote,
                                                  mask_sign_curly)
        if pos == 0:
            break

        masked_single_quote = masked_curly_brace

    # Todo is this correct? - in original, mask00 (masked_curly_brace) is modified as `mask += mask00[pos:]`, not mask0
    # Finally, look for triple quote regions in masked_single_quote, and mask them out
    mask, _ = mask_characters(triple_quote_match, masked_single_quote, masked_single_quote, mask_sign_triple_quote)
    # Now split the mask into newlines. Newlines inside curly blocks will have been masked out
    lines = []
    pos = 0
    for line in mask.split("\n"):
        end_pos = pos + len(line)
        block = spytext[pos:end_pos]

        if block:
            lines.append(block)

        pos = end_pos + len("\n")

    return lines


def parse_block(blocktext):
    """
    Parses the content of a block into four parts
    - Block type: the first word
    - Block head: the first line after the block type, before the curly braces
    - Block: content between curly braces (None if no_func_required curly braces)
    - Block docstring: commented content right after the start of the block
    """
    masked_triple_quote, _ = mask_characters(triple_quote_match, blocktext, blocktext, mask_sign_triple_quote)
    masked_single_quote, _ = mask_characters(single_quote_match, masked_triple_quote, blocktext, mask_sign_single_quote)

    pre_block = blocktext
    post_block = ""
    blocks = []

    while True:
        pos = 0
        masked_curly_braces = ""
        block_contents = []
        for match in curly_brace_match.finditer(masked_single_quote):
            block_contents.append(blocktext[match.start():match.end()])
            pre_block = blocktext[pos:match.start()]
            masked_curly_braces += pre_block + mask_sign_curly * (match.end() - match.start())
            pos = match.end()

        masked_curly_braces += masked_single_quote[pos:]

        if pos == 0:
            break

        else:
            post_block = blocktext[pos:]

        blocks = block_contents
        masked_single_quote = masked_curly_braces

    if len(blocks) > 1:
        raise SpyderParseError("compile error: invalid statement\n%s\nStatement must contain a single {} block" % blocktext)

        if post_block.strip():
            raise SpyderParseError("compile error: invalid statement\n%s\nStatement must be empty after {} block" % blocktext)

    elif blocks:
        block = blocks[0][1:-1]

    else:
        block = None

    pre_block = pre_block.strip()
    pre_block_masked_single_quote, _ = mask_characters(single_quote_match, pre_block, pre_block, mask_sign_single_quote)

    # Find docstring
    comment_start = pre_block_masked_single_quote.find("#")
    if comment_start > -1:
        block_docstring = pre_block[comment_start+1:].strip('\n') + '\n'
        pre_block = pre_block[:comment_start]

    else:
        block_docstring = ""

    if block is not None:
        current_block = block

        while True:
            original_length = len(current_block)
            current_block = current_block.lstrip().lstrip("\n")

            if len(current_block) == original_length:
                break

        match = triple_quote_match.search(current_block)
        if match is not None and match.start() == 0:
            block_docstring += current_block[match.start()+len('"""'):match.end()-len('"""')]

    else:
        match = triple_quote_match.search(blocktext)
        if match is not None and match.start() == 0:
            match0, match1 = match.start() + len('"""'), match.end()-len('"""')
            block_docstring = blocktext[match0:match1]
            pre_block = blocktext[:match.start()]

    block_type = None
    block_head = None

    if pre_block:
        block_type = pre_block.split()[0]
        block_head = pre_block[len(block_type):].strip()

    return BlockParseResult(block_type, block_head, block, block_docstring)
