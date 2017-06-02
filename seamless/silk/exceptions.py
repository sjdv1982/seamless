import re, traceback, sys


class SilkError(Exception):
    """Generic silk error"""


class SilkParseError(SilkError):
    """Silk parsing error"""


class SilkSyntaxError(SilkError, SyntaxError):
    """Silk syntax error"""

curly_brace_match = re.compile(r'{[^{}]*?}')


class SilkValidationError(SilkError):
    def __str__(self):
        message, glob, loc = self.args
        message_expr = ""
        curpos = 0
        for p in curly_brace_match.finditer(message):
            message_expr += message[curpos:p.start()]
            expr = p.group(0)[1:-1]
            try:
                expr_result = str(eval(expr, glob, loc))
            except Exception:
                expr_result = "{" + "".join(
                    traceback.format_exception_only(
                        *sys.exc_info()[:2]
                    )
                ).replace("\n", "") + "}"
            message_expr += expr_result
            curpos = p.end()
        message_expr += message[curpos:]
        return message_expr
