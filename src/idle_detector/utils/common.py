import asyncio
import re
from datetime import datetime
from decimal import Decimal
from os import PathLike as _PathLike
from typing import Any, Callable, Union

PathLike = Union[str, _PathLike]
DEFAULT_START_TIME_INTERVAL = 120
DISPLAY_WAS_OFF = False
IS_IDLE_START_TIME = Decimal(1e-1)
IDLE_DETECTOR_RUN = False


def current_timestamp():
    """Return the current local date and time."""
    return datetime.now()


def validate_interval_value(interval, default=DEFAULT_START_TIME_INTERVAL):
    """
    Validate and return a non-zero numerical interval.
    If the provided interval is invalid (e.g., None or 0), return the default.
    """
    return interval if is_valid_object(interval) else default


def is_valid_object(num):
    """
    Validate numerical or time-based configuration values.
    Specifically ensures that display monitor/sleep intervals set to `0` are treated as invalid.
    """
    return bool(num)


def type_name(obj: object) -> str:
    """
    Return a clean, human-readable type name for debugging or logs.
    Handles both instances and classes safely, falling back to qualified names if necessary.
    """
    if not isinstance(obj, type):
        obj = type(obj)

    def _gattr(n):
        return getattr(obj, n, None)

    return _gattr("__name__") or _gattr("__qualname__") or repr(obj)


def regex_compiler(pattern: str):
    """
    Compile a regex with consistent flags across the codebase:
    - IGNORECASE for non-sensitive matching.
    - MULTILINE for log parsing where ^ and $ span multiple lines.
    """
    return re.compile(pattern, flags=re.IGNORECASE | re.MULTILINE)


def regex_search(pattern: str, string: str):
    return regex_compiler(pattern).search(string)


def regex_findall(pattern: str, string: str):
    return regex_compiler(pattern).findall(string)


def encode_message(message):
    """
    Encode a message to UTF-8 bytes if possible.
    Used for subprocess-safe string transmission and file IO consistency.
    """
    if hasattr(message, "encode") and callable(getattr(message, "encode", None)):
        message = message.encode("utf-8")
    return message


def to_seconds(seconds):
    """
    Normalize a variety of time objects into raw seconds (float or Decimal).
    Handles timedelta-like/namespace objects with `seconds` or `total_seconds()` attributes.
    Returns None if the input is missing or incompatible.
    """
    if seconds is None:
        return

    if hasattr(seconds, "seconds"):
        seconds = seconds.seconds
    elif hasattr(seconds, "total_seconds"):
        seconds = seconds.total_seconds()
    return seconds


async def run_in_thread(func: Callable[..., Any], *args, **kwargs) -> Any:
    """
    Run a synchronous callable in the default executor and return the result.
    Use this to wrap blocking I/O (run_process, Quartz calls, etc.) so the
    event loop is not blocked.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))
