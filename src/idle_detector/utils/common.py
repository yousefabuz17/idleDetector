import re
from os import PathLike as _PathLike
from typing import Union

PathLike = Union[str, _PathLike]
DEFAULT_SLEEP_START_TIME = 120


def type_name(obj: object) -> str:
    if not isinstance(obj, type):
        obj = type(obj)

    def _gattr(n):
        return getattr(obj, n, None)

    return _gattr("__name__") or _gattr("__qualname__") or repr(obj)


def regex_compiler(pattern: str):
    return re.compile(pattern, flags=re.IGNORECASE | re.MULTILINE)


def regex_search(pattern: str, string: str):
    return regex_compiler(pattern).search(string)


def encode_message(message: str = ""):
    return message.encode("utf-8")
