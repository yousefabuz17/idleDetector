from argparse import ArgumentParser

from ..idle_detector import idleDetector
from ..log.root_logger import get_logger
from ..utils.common import PROJECT
from ..utils.os_modules import terminate
from .functions import CliFormatter, get_metadata, has_flag, store_false, store_true


async def cli_parser():
    # ============= Core Setup ================
    arg_parser = ArgumentParser(
        description=PROJECT,
        formatter_class=CliFormatter,
    )
    logger = await get_logger(stream_only=True, include_timestamp=False)
    ap_true = store_true(arg_parser.add_argument)
    ap_false = store_false(arg_parser.add_argument)
    
    # =================================================

    # ============= `Metadata` Flags ================
    ap_true(
        "--author", help=f"Print the name of the author of the '{PROJECT}' project."
    )
    ap_true("--url", help="Show the project’s homepage or repository URL.")
    ap_true("--version", help=f"Print the current version of '{PROJECT}'.")
    # =================================================
    
    
    # ============= `idleDetector` Flags ================
    ap_true(
        "--run-in-background",
        help="Run idle-detector in the background as a daemon/service.",
    )
    ap_true("--compact-time", help="Display idle time in a compact format. E.g., '5m 30s' instead of '5 minutes, 30 seconds'.")
    ap_true(
        "--group-notifications",
        help="Group notifications by their type to reduce clutter.",
    )
    ap_false(
        "--consider-screensaver-as-off",
        help="This will treat the screensaver activation as if the display has been turned off. A wake-up message will be sent when the screensaver is dismissed.",
    )
    ap_false(
        "--honor-dnd",
        help="Honor Do Not Disturb settings; respect them when sending notifications.",
    )
    arg_parser.add_argument(
        "-c",
        "--custom-idle-time",
        type=int,
        default=300,
        help="Set a custom idle time threshold (in seconds). Please note, this will only work if no other idle modes are set.",
    )
    arg_parser.add_argument(
        "-p",
        "--pause-detection",
        type=int,
        help="Set a custom idle time threshold (in seconds: int | float). Please note, this will only work if no other idle modes are set.",
    )
    arg_parser.set_defaults(
        consider_screensaver_as_off=False,
        honor_dnd=False
    )

    args = arg_parser.parse_args()
    metadata = get_metadata()

    for k, v in metadata.items():
        if has_flag(args, k):
            logger.info(v)
            terminate()
    
    async with idleDetector(
        ignoreDnD=args.honor_dnd,
        compact_timestamp=args.compact_time,
        idle_interval_if_no_modes_are_set=args.custom_idle_time,
        consider_screensaver_as_off=args.consider_screensaver_as_off,
        group_notifications=args.group_notifications,
        pause_detection_timer=args.pause_detection
    ) as idle_detector:
        await idle_detector.start_idle_detection()
