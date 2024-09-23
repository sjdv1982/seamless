from .rules import rule_to_str

class ExpectedExpr:
    def __init__(self, expr, callstack):
        self.expr = expr
        self.callstack = callstack

class UnexpectedExpr:
    def __init__(self, end_pos, rule, callstack):
        self.end_pos = end_pos
        self.rule = rule
        self.callstack = callstack

class SemanticFailure:
    def __init__(self, args, kw, callstack):
        self.args = args
        self.kw = kw
        self.callstack = callstack

class ParseError(RuntimeError):
    def __init__(self, message, text, start_pos, end_pos, failures):
        self.message = message
        self.text = text
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.failures = failures

    def __str__(self):
        return 'at {}:{}: {}'.format(
            self.start_pos.line, self.start_pos.col, self.message)

def _first(iterable):
    return next(iterable, None)

def raise_parsing_error(text, position, failures):
    end_pos = position
    msg = []

    sema = _first(f for f in failures if isinstance(f, SemanticFailure))
    if sema is not None:
        msg.append(sema.args[0])
    else:
        unexps = [f for f in failures if isinstance(f, UnexpectedExpr)]
        if unexps:
            unexp = min(unexps,
                key=lambda f: f.end_pos.offset - position.offset)
            end_pos = unexp.end_pos
            msg.append('unexpected {}'.format(rule_to_str(unexp.rule)))

        exps = [f for f in failures if isinstance(f, ExpectedExpr)]
        if exps:
            exp_syms = set()
            for f in exps:
                r = _first(se.fn for se in f.callstack
                    if se.position == position and not getattr(se.fn, '_speg_hidden', False))
                if r is None:
                    r = f.expr
                exp_syms.add(rule_to_str(r))
            exp_strs = sorted(exp_syms)

            if len(exp_strs) == 1:
                msg.append('expected {}'.format(exp_strs[0]))
            else:
                msg.append('expected one of {}'.format(', '.join(exp_strs)))

    raise ParseError('; '.join(msg), text, position, end_pos, failures)
