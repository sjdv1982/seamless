"""
Adapted and improved from:

Bytes-to-human / human-to-bytes converter.
Based on: http://goo.gl/kTQMs
Working with Python 2.x and 3.x.

Author: Giampaolo Rodola' <g.rodola [AT] gmail [DOT] com>
License: MIT

https://code.activestate.com/recipes/578019-bytes-to-human-human-to-bytes-converter/
"""

SYMBOLS = {
    "decimal": ("B", "kB", "MB", "GB", "TB", "PB"),
    "decimal2": ("bytes", "kB", "MB", "GB", "TB", "PB"),
    "decimal_ext": (
        "bytes",
        "kilobytes",
        "megabytes",
        "gigabytes",
        "terabytes",
        "petabytes",
    ),
    "memory": ("bytes", "KB", "MB", "GB", "TB"),
    "memory2": ("B", "K", "M", "G", "T"),
    "binary": ("B", "KiB", "MiB", "GiB", "TiB", "PiB"),
    "binary2": ("bytes", "KiB", "MiB", "GiB", "TiB", "PiB"),
    "binary_ext": (
        "bytes",
        "kibibytes",
        "mebibytes",
        "gibibytes",
        "tebibytes",
        "pebibytes",
    ),
}


def bytes2human(
    n, format="%(value).1f %(symbol)s", symbols="decimal"
):  # pylint: disable=redefined-builtin
    """
    Convert n bytes into a human readable string based on format.
    """
    n = int(n)
    if n < 0:
        raise ValueError("n < 0")
    sset = SYMBOLS[symbols]
    prefix = {}
    if symbols.startswith("decimal"):
        for i, s in enumerate(sset[1:]):
            prefix[s] = 1000 ** (i + 1)
    else:
        for i, s in enumerate(sset[1:]):
            prefix[s] = 1 << (i + 1) * 10
    for symbol in reversed(sset[1:]):
        if n >= prefix[symbol]:
            value = float(n) / prefix[symbol]  # pylint: disable=W0641
            return format % locals()
    return format % dict(symbol=sset[0], value=n)


def human2bytes(s):
    """
    Attempts to guess the string format based on default symbols
    set and return the corresponding bytes as an integer.
    When unable to recognize the format ValueError is raised.
    """
    init = s
    num = ""
    while s and s[:1].isdigit() or s[:1] == ".":
        num += s[0]
        s = s[1:]
    num = float(num)
    if not s:
        return int(num)
    letter = s.strip()

    if letter == "k":
        # treat 'k' as an alias for 'K' as per: http://goo.gl/kTQMs
        letter = letter.upper()

    symbol_sets = [k for k in SYMBOLS if k.startswith("decimal")]
    symbol_sets += [k for k in SYMBOLS if k not in symbol_sets]

    for symbol_set in symbol_sets:
        sset = SYMBOLS[symbol_set]
        if letter in sset:
            break
    else:
        raise ValueError("can't interpret %r" % init)
    prefix = {sset[0]: 1}
    if symbol_set.startswith("decimal"):
        for i, s in enumerate(sset[1:]):
            prefix[s] = 1000 ** (i + 1)
    else:
        for i, s in enumerate(sset[1:]):
            prefix[s] = 1 << (i + 1) * 10
    return int(num * prefix[letter])
