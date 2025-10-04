from typing import Optional

from platformdirs.macos import MacOS
from Quartz import (
    CGEventSourceSecondsSinceLastEventType,
    kCGAnyInputEventType,
    kCGEventSourceStateCombinedSessionState,
)

from ..utils.common import regex_search
from ..utils.exceptions import MachineNotSupported
from ..utils.os_modules import get_platform, run_process


def get_sleep_idle_time() -> Optional[int]:
    """Return screen saver idle time in seconds. None if not set or error."""
    try:
        output = run_process(
            ("defaults", "-currentHost", "read", "com.apple.screensaver", "idleTime")
        ).stdout
        idle_time = int(output.strip())
        return idle_time
    except Exception:
        pass


def get_display_off_time(seconds: bool = True) -> Optional[int]:
    """Return display sleep time. Defaults to seconds. Returns None if not set."""
    try:
        output = run_process(("pmset", "-g")).stdout
        search_sleep_time = regex_search(r"displaysleep\s+(\d+)", output)

        if not search_sleep_time:
            return

        sleep_time = int(search_sleep_time.group(1))
        return sleep_time * 60 if seconds else sleep_time
    except Exception:
        pass


def current_idle_time() -> float:
    """Return current idle time in seconds since last input event."""
    try:
        return CGEventSourceSecondsSinceLastEventType(
            kCGEventSourceStateCombinedSessionState, kCGAnyInputEventType
        )
    except Exception:
        return 0.0


class macOS(MacOS):
    MACHINE: str = get_platform()  # `darwin`
    current_idle_time: float = staticmethod(current_idle_time)
    get_display_off_time: float = staticmethod(get_display_off_time)
    get_sleep_idle_time: float = staticmethod(get_sleep_idle_time)

    def __init__(
        self,
        appname: Optional[str] = None,
        ensure_exists: bool = False,
        auto_check_machine: bool = True,
    ):
        super().__init__(appname, ensure_exists)

        if auto_check_machine:
            self.check_machine()

    def check_machine(self):
        machine = self.MACHINE
        if machine != "darwin":
            raise MachineNotSupported(
                f"Detected OS {machine!r} ❌ - this script is strictly built for MacOS (darwin) only."
            )
