import asyncio
from argparse import ArgumentDefaultsHelpFormatter, RawTextHelpFormatter
from functools import partial

from ..models._dataclasses import SerializedNamespace
from ..utils.common import PAUSE_DETECTION_TIMER
from ..utils.os_modules import terminate


class CliFormatter(RawTextHelpFormatter, ArgumentDefaultsHelpFormatter):
    pass


async def clean_terminate(status: int = 0):
    await asyncio.sleep(PAUSE_DETECTION_TIMER)
    terminate(status)


def store_true(func, *args, **kwargs):
    kwargs["action"] = kwargs.pop("action", "store_true")
    return partial(func, *args, **kwargs)


def store_false(func, *args, **kwargs):
    kwargs["action"] = "store_false"
    return store_true(func, *args, **kwargs)


def has_flag(parsed_arg, attr):
    return getattr(parsed_arg, attr, None)


def get_metadata():
    from ..utils.metadata import (
        __author__,
        __url__,
        __version__,
    )

    return SerializedNamespace(
        module="Metadata", author=__author__, url=__url__, version=__version__
    )
