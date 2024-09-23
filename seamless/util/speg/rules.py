from six import string_types

class Eof: pass
eof = Eof()

def rule_to_str(rule):
    if rule is eof:
        return 'eof'
    if isinstance(rule, string_types):
        return repr(rule)
    fn_name = rule.__name__
    if fn_name.startswith('_'):
        fn_name = fn_name[1:]
    return '<{}>'.format(fn_name.replace('_', ' '))
