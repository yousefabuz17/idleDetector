from argparse import ArgumentParser
from functools import partial

from ..agent.install import AgentInstaller
from ..idle_detector import idleDetector
from ..log.root_logger import get_logger
from ..models._dataclasses import SerializedNamespace
from ..models.machine import MacOS
from ..utils.common import PROJECT
from ..utils.os_modules import terminate
from .functions import (
    CliFormatter,
    clean_terminate,
    get_metadata,
    has_flag,
    store_false,
    store_true,
)


async def cli_parser():
    # ============= Core Setup ================
    arg_parser = ArgumentParser(
        description=PROJECT,
        formatter_class=CliFormatter,
    )
    subparsers = arg_parser.add_subparsers(dest="command", help="All Command Options.")
    ap_true = store_true(arg_parser.add_argument)
    ap_false = store_false(arg_parser.add_argument)

    launch_agent_flag = subparsers.add_parser(
        "launch-agent",
        description="Install or manage the launch agent for idle-detector.",
        formatter_class=CliFormatter,
        aliases=(la_aliases := ("agent", "la")),
        help="Install or manage the launch agent for idle-detector.",
    )
    lp_true = store_true(launch_agent_flag.add_argument)

    mac_os_flag = subparsers.add_parser(
        "machine",
        description="Retrieve macOS system information.",
        formatter_class=CliFormatter,
        aliases=(mac_aliases := ("mac", "macos", "mac-os")),
        help="Retrieve macOS system information.",
    )
    mp_true = store_true(mac_os_flag.add_argument)

    logger = await get_logger(stream_only=True, include_timestamp=False)
    # =================================================

    # ============= `Metadata` Flags ================
    ap_true("--author", help=f"Print the author of '{PROJECT}'.")
    ap_true("--url", help="Show project repository URL.")
    ap_true("--version", help=f"Print '{PROJECT}' version.")
    # =================================================

    # ============= `AgentInstaller` Flags ================
    lp_true("-i", "--install", help="Install the LaunchAgent.")
    lp_true("-r", "--register", help="Register (bootstrap) the agent.")
    lp_true("-D", "--deregister", help="Unregister (bootout) the agent.")
    lp_true("-e", "--enable", help="Enable the agent.")
    lp_true("-d", "--disable", help="Disable the agent.")
    lp_true("-s", "--start-now", help="Start the agent immediately.")
    lp_true("-f", "--full-install", help="Full install: register, enable, start.")
    lp_true("-F", "--full-uninstall", help="Full uninstall: deregister agent.")
    lp_true("-R", "--refresh-agent", help="Refresh (restart) the LaunchAgent.")
    lp_true("-C", "--check-agent", help="Check if LaunchAgent is running.")

    # ============= `MacOS` Flags ================
    mp_true("--os-machine", help="Return the system platform identifier.")
    mp_true("--mac-version", help="Return the macOS version as a string.")
    mp_true("--hostname", help="Return the system's network node name.")
    mp_true(
        "--log-files",
        help="Return standard log file paths used by idle-detector on macOS.",
    )
    mp_true("--username", help="Return the current logged-in macOS username.")
    # =================================================

    # ============= `idleDetector` Flags ================
    ap_true(
        "--compact-time",
        help="Display idle time in a compact format. E.g., '5m 30s' instead of '5 minutes, 30 seconds'.",
    )
    ap_true(
        "--group-notifications",
        help="Group notifications by their type to reduce clutter.",
    )
    ap_false(
        "--consider-screensaver-as-off",
        help=(
            "This will treat the screensaver activation as if the display has been turned off. "
            "A wake-up message will be sent when the screensaver is dismissed."
        ),
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
        help=(
            "Set a custom idle time threshold (in seconds). "
            "Please note, this will only work if no other idle (screensaver/display-off) modes are set."
        ),
    )

    arg_parser.set_defaults(consider_screensaver_as_off=False, honor_dnd=False)

    parsed_args = arg_parser.parse_args()

    args = SerializedNamespace(module="ArgsNamespace", **parsed_args.__dict__)
    metadata = get_metadata()
    arg_has_flag = partial(has_flag, args)
    requires_help_page = False
    flag_is_for_machine = False
    flag_is_for_metadata = False
    agent_installer = AgentInstaller()

    for k, v in metadata.items():
        if arg_has_flag(k):
            flag_is_for_metadata = True
            logger.info(v)
    else:
        if flag_is_for_metadata:
            terminate()

    if flag := args.command:
        if flag == "launch-agent" or flag in la_aliases:
            if args.refresh_agent:
                agent_installer.build_agent()
                await clean_terminate()

            if args.check_agent:
                logger.info(agent_installer.is_booted_already)
                await clean_terminate()

            has_agent_flag = any(
                any(
                    (
                        has_flag(AgentInstaller, k),
                        has_flag(AgentInstaller, f"{k}_agent"),
                    )
                )
                and bool(v)
                for k, v in args.items()
            )

            if has_agent_flag:
                idleDetector.launch_agent(
                    register=args.register,
                    deregister=args.deregister,
                    enable=args.enable,
                    disable=args.disable,
                    start_now=args.start_now,
                    full_install=args.full_install,
                    full_uninstall=args.full_uninstall,
                )
                await clean_terminate()
            else:
                requires_help_page = True
        elif flag == "machine" or flag in mac_aliases:
            mac = MacOS()
            available_attrs = (
                "log_files",
                "os_machine",
                "mac_version",
                "hostname",
                "username",
            )
            for a in available_attrs:
                if arg_has_flag(a):
                    flag_is_for_machine = True
                    mac_func = getattr(mac, a)
                    if callable(mac_func):
                        mac_func = mac_func()
                    logger.info(mac_func)
            else:
                requires_help_page = not flag_is_for_machine

    if requires_help_page:
        # If flag given was a command but no
        # arguments was provided for it.
        # Output the help page for further assistance.
        logger.warning(f"No arguments were provided for the {args.command!r} command.")
        arg_parser.print_help()
        terminate(status=1)

    async with idleDetector(
        ignoreDnD=args.honor_dnd,
        compact_timestamp=args.compact_time,
        idle_interval_if_no_modes_are_set=args.custom_idle_time,
        consider_screensaver_as_off=args.consider_screensaver_as_off,
        group_notifications=args.group_notifications,
    ) as idle_detector:

        if arg_has_flag("check_agent"):
            logger.info(idle_detector.is_booted_already)
            await clean_terminate()

        await idle_detector.start_idle_detection()
