from functools import total_ordering

@total_ordering
class Position(object):
    def __init__(self, offset=0, line=1, col=1):
        self.offset = offset
        self.line = line
        self.col = col

    def advanced_by(self, text):
        text_len = len(text)
        offset = self.offset + text_len
        nl_pos = text.rfind('\n')
        if nl_pos < 0:
            line = self.line
            col = self.col + text_len
        else:
            line = self.line + text[:nl_pos].count('\n') + 1
            col = text_len - nl_pos
        return Position(offset, line, col)

    def __eq__(self, other):
        if not isinstance(other, Position):
            return NotImplemented
        return self.offset == other.offset

    def __ne__(self, other):
        return not self == other

    def __hash__(self):
        return hash(self.offset)

    def __lt__(self, other):
        if not isinstance(other, Position):
            return NotImplemented
        return self.offset < other.offset

    def __repr__(self):
        return '{}({!r}, {!r}, {!r})'.format(Position.__name__,
            self.offset, self.line, self.col)

def get_line_at_position(text, pos):
    suffix = text[pos.offset - pos.col + 1:]
    stop = suffix.find('\n')
    if stop == -1:
        return suffix, pos.col - 1
    else:
        return suffix[:stop], pos.col - 1
