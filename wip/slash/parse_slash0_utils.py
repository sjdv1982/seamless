import re
double_quote = re.compile(r'(\A|[^\\])\"')
single_quote = re.compile(r"(\A|[^\\])\'")
token_separators=r'(?P<sep1>[\s]+)|[\s](?P<sep2>2>)[^&][^1]|[\s](?P<sep3>!>)[\s]|[\s](?P<sep4>2>&1)|[^2!](?P<sep5>>)'
token_separators = re.compile(token_separators)

def tokenize(text, masked_text):
    tokens = []
    pos = 0
    for match in token_separators.finditer(masked_text):
        seps = match.groupdict()
        split_tokens = [v for v in seps.values() if v is not None]
        assert len(split_tokens) == 1, seps
        split_token = split_tokens[0].strip()
        if len(split_token):
            tokens.append(split_token)
        newpos = match.start()
        if pos != newpos:
            tokens.append(text[pos:newpos])
        pos = match.end()
    tokens.append(text[pos:])
    return tokens
