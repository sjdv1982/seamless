"""Seamless utilities"""

from typing import Any

from seamless import Checksum

from .pylru import lrucache
from .cson import cson2json


class lrucache2(lrucache):
    """Version of lrucache that can be disabled"""

    _disabled = False

    def disable(self):
        """Disable this LRU cache"""
        self._disabled = True

    def enable(self):
        """Enable this LRU cache"""
        del self._disabled

    def __setitem__(self, key, value):
        if self._disabled:
            return
        super().__setitem__(key, value)


def parse_checksum(checksum, as_bytes=False):
    """Parses checksum and returns it as string
    If as_bytes is True, return it as bytes instead."""

    if isinstance(checksum, Checksum):
        checksum = checksum.bytes()
    if isinstance(checksum, bytes):
        checksum = checksum.hex()
    if isinstance(checksum, str):
        checksum = bytes.fromhex(checksum)

    if isinstance(checksum, bytes):
        if len(checksum) != 32:
            raise ValueError(f"Incorrect length: {len(checksum)}, must be 32")
        if as_bytes:
            return checksum
        else:
            return checksum.hex()

    if checksum is None:
        return
    raise TypeError(type(checksum))


def _unchecksum_dict(d: dict) -> dict:
    """Return a copy of d where Checksum instances have been changed to str"""
    return {k: unchecksum(v) for k, v in d.items()}


def _unchecksum_list(l: list | tuple) -> list:
    """Return a copy of l where Checksum instances have been changed to str"""
    return [unchecksum(v) for v in l]


def unchecksum(value: Any) -> Any:
    """Return value or a copy of value where Checksum instances have been changed to str"""
    if isinstance(value, Checksum):
        return value.value
    elif isinstance(value, dict):
        return _unchecksum_dict(value)
    elif isinstance(value, (list, tuple)):
        return _unchecksum_list(value)
    else:
        return value
