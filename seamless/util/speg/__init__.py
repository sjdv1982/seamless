from .errors import ParseError, ExpectedExpr, UnexpectedExpr, SemanticFailure
from .peg import Parser
from .rules import eof

def peg(text, root_rule):
    p = Parser(text)
    return p(root_rule)

def parse(text, root_rule):
    p = Parser(text)
    return p.parse(root_rule)

def hidden(fn):
    fn._speg_hidden = True
    return fn