from argparse import ArgumentDefaultsHelpFormatter, RawTextHelpFormatter
from functools import partial


class CliFormatter(RawTextHelpFormatter, ArgumentDefaultsHelpFormatter):
    pass


def store_true(func, *args, **kwargs):
    kwargs["action"] = kwargs.pop("action", "store_true")
    return partial(func, *args, **kwargs)


def store_false(func, *args, **kwargs):
    kwargs["action"] = "store_false"
    return store_true(func, *args, **kwargs)


def has_flag(parsed_arg, attr):
    return hasattr(parsed_arg, attr) and getattr(parsed_arg, attr)


def get_metadata():
    from ..utils.metadata import (
        __author__,
        __url__,
        __version__,
    )

    return dict(author=__author__, url=__url__, version=__version__)
