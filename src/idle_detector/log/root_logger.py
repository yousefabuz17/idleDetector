import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from ..models.machine import MacOS
from ..utils.common import PROJECT, PathLike
from ..utils.os_modules import rename, rm_file

Logger = logging.Logger


class RotateLogHandler(RotatingFileHandler):
    """Custom rotating log handler with controlled suffix logic."""

    def rotation_filename(self, default_name: PathLike):
        """
        Returns the proper rotated filename for a given log file path.
        Ensures numeric suffix ordering and consistent `.log` extension.
        """

        def clean_suffix(suffix):
            return suffix.removeprefix(".")

        def is_default_file(suffixes):
            return suffixes[0] == "log" and len(suffixes) == 1

        def is_invalid_file_type(suffixes):
            possible_digit = suffixes[-1]
            return possible_digit.isnumeric()

        default_name = Path(default_name)
        suffixes = list(map(clean_suffix, default_name.suffixes))

        if not is_invalid_file_type(suffixes) or (
            not suffixes or is_default_file(suffixes)
        ):
            current_log_file = default_name
        else:
            suffixes = ".".join(suffixes[::-1])
            current_log_file = default_name.with_suffix(f".{suffixes}")

        return current_log_file

    def doRollover(self):
        """
        Performs rollover as in the base `RotatingFileHandler`,
        but with consistent cleanup and naming logic.
        """

        # Copied and modified code from `RotatingFileHandler.doRollover`
        if self.stream:
            self.stream.close()
            self.stream = None

        if self.backupCount > 0:
            base_filename = Path(self.baseFilename)

            for i in range(self.backupCount - 1, 0, -1):
                sfn = self.rotation_filename(base_filename.with_suffix(f".{i}.log"))
                dfn = self.rotation_filename(base_filename.with_suffix(f".{i + 1}.log"))

                if sfn.exists():
                    rm_file(dfn)
                    rename(sfn, dfn)

            dfn = self.rotation_filename(base_filename.with_suffix(".1.log"))
            rm_file(dfn)

            self.rotate(self.baseFilename, dfn)

        if not self.delay:
            self.stream = self._open()


async def get_logger(stream_only: bool = False, include_timestamp: bool = True):
    """
    Returns a preconfigured logger for macOS environments.
    When stream_only=True: logs only to console
    When stream_only=False: logs to both console and file
    """
    mac_machine = MacOS(f"{PROJECT}.log", ensure_exists=True)
    await mac_machine.check_machine()

    DEFAULT_LOG_FILE = mac_machine.user_log_dir
    MAX_LOG_SIZE = 10_000_000  # 10 MB
    MAX_LOG_FILES = 5

    root_logger = logging.getLogger()

    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    level = logging.INFO

    fmt = "{}%(message)s".format("" if not include_timestamp else "[%(asctime)s]--")
    formatter = logging.Formatter(
        fmt=fmt,
        datefmt="%Y-%m-%dT%I:%M:%S%p",
    )

    stream_handler = logging.StreamHandler()
    stream_handler.setLevel(level)
    stream_handler.setFormatter(formatter)
    root_logger.addHandler(stream_handler)

    if not stream_only:
        file_handler = RotateLogHandler(
            DEFAULT_LOG_FILE,
            mode="a",
            encoding="utf-8",
            maxBytes=MAX_LOG_SIZE,
            backupCount=MAX_LOG_FILES,
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    root_logger.setLevel(level)

    return root_logger
