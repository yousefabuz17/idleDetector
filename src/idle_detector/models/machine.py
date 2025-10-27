import asyncio
import operator
from datetime import datetime
from decimal import Decimal
from functools import cached_property, lru_cache
from typing import ClassVar, Optional

from platformdirs.macos import MacOS as _MacOS
from Quartz import (
    CGDisplayIsActive,
    CGEventSourceSecondsSinceLastEventType,
    CGMainDisplayID,
    kCGAnyInputEventType,
    kCGEventSourceStateCombinedSessionState,
)

from ..utils.common import (
    PROJECT,
    compare_versions,
    current_timestamp,
    date_parser,
    regex_findall,
    run_async_process,
    run_in_thread,
    type_name,
    validate_interval_value,
)
from ..utils.exceptions import (
    MachineNotSupported,
    UndetectableIdleState,
)
from ..utils.os_modules import (
    get_env,
    get_mac_version,
    get_nodename,
    get_platform,
    run_process,
)
from ._dataclasses import SerializedNamespace, TimeTypes
from .time_handler import idleSeconds


# ---------------------------
# Low-level async wrappers
# ---------------------------
async def get_screensaver_time():
    """
    Retrieve the system's screensaver idle delay (in seconds).

    Returns:
        Optional[int]: The configured screensaver activation delay, or `None` if not available.
    """
    try:
        cmd = ["defaults", "-currentHost", "read", "com.apple.screensaver", "idleTime"]
        process = await run_async_process(cmd)
        output = process.stdout
        return int(output.strip())
    except (Exception, ValueError):
        # Avoid returning 0 for unset preferences (interpreted as disabled)
        pass


async def get_display_off_time(seconds: bool = True):
    """
    Retrieve display sleep time configured in macOS Power Management (pmset).

    Args:
        seconds (bool): If True, converts minutes into seconds. Default True.

    Returns:
        Optional[int|float]: Display sleep duration in requested unit, or None if undetectable.
    """
    try:
        process = await run_async_process(["pmset", "-g"])
        output = process.stdout
        search_sleep_time = [
            i.split()[1]
            for i in output.splitlines()
            if i.strip().startswith("displaysleep")
        ]
        if search_sleep_time:
            sleep_time = int(search_sleep_time[0])
            return sleep_time * TimeTypes.MINUTES if seconds else sleep_time
    except Exception:
        pass


async def _get_display_log_details(
    display_is_turned_off: bool = False,
) -> SerializedNamespace:
    """
    Extract the most recent display on/off event from `pmset -g log`.

    Returns a SerializedNamespace with:
      - event_date: datetime | None
      - total_seconds: int | None
      - is_reached: bool
    """
    display_mode_regex = "off" if display_is_turned_off else "on"
    ns = SerializedNamespace(module="Display" + display_mode_regex.capitalize())
    ns.event_date = None
    ns.total_seconds = None
    ns.is_reached = False

    try:
        proc = await run_async_process(["pmset", "-g", "log"])
        output = proc.stdout
        pattern = r".*Notification\s+Display is turned {}".format(display_mode_regex)
        display_mode_detail = regex_findall(pattern, output)

        if display_mode_detail:
            last_event = display_mode_detail[-1]
            # timestamp appears as "YYYY-MM-DD HH:MM:SS -zzzz"
            last_event_date = last_event.split()[:2]
            last_event_dt = date_parser(" ".join(last_event_date))
            ns.event_date = last_event_dt
            ns.total_seconds = await calculate_seconds_since_last_event(last_event_dt)
            ns.is_reached = ns.total_seconds is not None and ns.total_seconds <= 30
    except Exception:
        # swallow parsing/read errors; return empty namespace
        pass

    return ns


async def calculate_seconds_since_last_event(event_date: datetime) -> Optional[int]:
    """
    Compute seconds elapsed between `event_date` and the current time.
    Returns integer seconds or None on error.
    """
    try:
        time_since_last_event = current_timestamp() - event_date
        total = time_since_last_event.total_seconds()
        return int(total)
    except Exception:
        return None


async def get_last_time_display_turned_on():
    return await _get_display_log_details(display_is_turned_off=False)


async def get_last_time_display_turned_off():
    return await _get_display_log_details(display_is_turned_off=True)


# ---------------------------
# System state checks
# ---------------------------
async def is_display_active(check_if_still_off: bool = False) -> bool:
    """
    Determine if the main display is active (not asleep).

    Strategy (in order):
      1. Query CGDisplayIsActive on main display (wrapped in executor).
      2. Check if screensaver is running (async).
      3. Fallback: compare last-on / last-off timestamps from pmset logs.

    Args:
        check_if_still_off: If True, invert result to signal whether display is still off.

    Returns:
        bool: True if display is active (or still off when check_if_still_off=True).
    """
    # 1) Try Quartz API (non-blocking because we run it in executor)
    try:
        active = await run_in_thread(CGDisplayIsActive, CGMainDisplayID())
        display_status = bool(active)
        return (not display_status) if check_if_still_off else display_status
    except Exception:
        # proceed to fallbacks
        pass

    # 2) Screensaver check
    try:
        if await is_screensaver_running():
            # If screensaver is running, treat display as "not active"
            return not check_if_still_off
    except Exception:
        pass

    # 3) Log-based inference (pmset)
    try:
        last_off = await get_last_time_display_turned_off()
        last_on = await get_last_time_display_turned_on()
        last_off_ts = last_off.event_date
        last_on_ts = last_on.event_date

        if not all((last_off_ts, last_on_ts)):
            # Insufficient data; default to "active"
            return not check_if_still_off

        # Compare the two events chronologically
        if check_if_still_off:
            # we want to know whether the last relevant event was "off"
            return operator.gt(last_off_ts, last_on_ts)
        else:
            return operator.gt(last_on_ts, last_off_ts)
    except Exception:
        # Final conservative fallback
        return not check_if_still_off


async def is_screensaver_running():
    """
    Check if the macOS screensaver is currently active.

    This asynchronous function uses AppleScript via the `osascript` command to determine
    whether the macOS screensaver is running. It executes the AppleScript command in a
    subprocess and parses the output to return a boolean value.

    Returns:
        bool: True if the screensaver is active, False otherwise. If the command fails
        or an exception occurs, it defaults to returning False.
    """
    try:
        proc = await run_async_process(
            [
                "osascript",
                "-e",
                'tell application "System Events" to get running of screen saver preferences',
            ]
        )
        result = proc.stdout.strip()
        # expected result: "true" or "false" or a capitalization variant
        # be defensive: map common text to booleans
        if not result:
            return False
        result_clean = result.strip().lower()
        return result_clean in ("true", "yes", "1")
    except Exception:
        return False


async def current_idle_time() -> idleSeconds:
    """
    Return system idle time as an `idleSeconds` wrapper (Decimal seconds).

    Primary: Quartz CGEventSourceSecondsSinceLastEventType (fast, wrapped in executor).
    Fallback: `ioreg` query (shell) to obtain HIDIdleTime and divide by 1e9.
    Raises UndetectableIdleState if both fail.
    """

    def fallback_idle_time_sync():
        try:
            shell_cmd = "ioreg -c IOHIDSystem | awk '/HIDIdleTime/ {print $NF/1000000000; exit}'"
            proc = run_process(shell_cmd)
            return float(proc.stdout.strip())
        except Exception:
            return None

    # Try Quartz API first (executed in thread to avoid any blocking)
    try:
        precise_idle = await run_in_thread(
            CGEventSourceSecondsSinceLastEventType,
            kCGEventSourceStateCombinedSessionState,
            kCGAnyInputEventType,
        )
    except Exception:
        precise_idle = None

    if not precise_idle:
        # fallback shell path (wrapped)
        precise_idle = await run_in_thread(fallback_idle_time_sync)

    if not precise_idle:
        raise UndetectableIdleState(
            "Unable to determine the system's idle time. The required system APIs are not accessible."
        )

    return idleSeconds(Decimal(precise_idle))


# ---------------------------
# region MacOS
# ---------------------------
class MacOS(_MacOS):
    MINIMUM_COMPATIBLE_VERSION: tuple = (10, 10)

    # Expose the top-level async helpers as staticmethods for parity with original design.
    current_idle_time: ClassVar[staticmethod] = staticmethod(current_idle_time)
    get_display_off_time: ClassVar[staticmethod] = staticmethod(get_display_off_time)
    get_screensaver_time: ClassVar[staticmethod] = staticmethod(get_screensaver_time)

    def __init__(self, appname: Optional[str] = None, ensure_exists: bool = False):
        super().__init__(appname=appname, ensure_exists=ensure_exists)

    def __str__(self):
        return "{}(user={!r}, hostname={!r}, mac_ver={!r}, appname={!r})".format(
            type_name(self),
            self.username,
            self.hostname,
            self.mac_version,
            self.appname,
        )

    async def check_machine(self):
        """
        Validate the host OS and macOS version compatibility.
        """
        if (machine := self.os_machine) != "darwin":
            raise MachineNotSupported(
                f"Detected OS {machine!r} ❌ - this script is strictly built for MacOS (darwin) only."
            )

        mac_version_tuple = tuple(int(v) for v in self.mac_version.split(".")[:2])
        await compare_versions(self, mac_version_tuple)

    @classmethod
    def generate_log_file(cls, file_name: str = None):
        if not file_name:
            file_name = PROJECT

        m = cls(ensure_exists=True)
        log_main_dir = m.user_log_path / PROJECT
        return (log_main_dir / file_name).with_suffix(".log")

    # --- synchronous cached properties (safe to compute quickly) ---
    @classmethod
    @lru_cache(maxsize=1)
    def log_files(cls):
        main_log_file, out_log, err_log = (
            MacOS().generate_log_file(f) for f in (None, "out", "err")
        )
        return SerializedNamespace(
            module="LogFiles", log_file=main_log_file, out_log=out_log, err_log=err_log
        )

    @cached_property
    def os_machine(self):
        """Return the system platform identifier, e.g., 'darwin'."""
        return get_platform()

    @cached_property
    def mac_version(self):
        """Return the macOS version string, e.g., '14.5'."""
        return get_mac_version()[0]

    @cached_property
    def hostname(self):
        """Return short system hostname (without .local suffix)."""
        return get_nodename().removesuffix(".local")

    @cached_property
    def username(self) -> Optional[str]:
        """Return the current logged-in username."""
        return get_env("USER") or get_env("LOGNAME")

    # --- async state-checks (methods, not properties) ---
    async def display_is_turned_on(self):
        """Check if the display remains in an 'on' state."""
        return await is_display_active(check_if_still_off=False)

    async def display_is_turned_off(self):
        """Check if the display remains in an 'off' (asleep) state."""
        return await is_display_active(check_if_still_off=True)

    async def screensaver_is_active(self):
        return await is_screensaver_running()

    # --- async cached getters for modes ---
    async def has_sleep_mode(self):
        """
        True if screensaver idle timeout is configured (not `None`, set to 0).
        """
        screensaver_time = await self.get_screensaver_time()
        return validate_interval_value(screensaver_time) is not None

    async def has_display_off_mode(self) -> bool:
        """
        True if display sleep mode is configured (not `None`, set to 0).
        """
        display_off_time = await self.get_display_off_time()
        return validate_interval_value(display_off_time) is not None

    async def modes_are_set(self, verify_both_are_set=True) -> bool:
        """
        Return True only if both sleep and display-off modes are active.
        """
        results = await asyncio.gather(
            self.has_sleep_mode(), self.has_display_off_mode()
        )
        method = any if not verify_both_are_set else all
        return method(results)
