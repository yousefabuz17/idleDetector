from typing import Optional

from platformdirs.macos import MacOS
from Quartz import (
    CGEventSourceSecondsSinceLastEventType,
    kCGAnyInputEventType,
    kCGEventSourceStateCombinedSessionState,
)

from ..utils.common import regex_search, type_name
from ..utils.exceptions import MachineNotSupported
from ..utils.os_modules import (
    get_env,
    get_mac_version,
    get_nodename,
    get_platform,
    run_process
)


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
    MINIMUM_COMPATIBLE_VERSION: tuple = (10, 8)
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
    
    def __str__(self):
        return "{}(user={!r}, hostname={!r})".format(
            type_name(self),
            self.username,
            self.hostname
        )

    def check_machine(self):
        if (machine := self.MACHINE) != "darwin":
            raise MachineNotSupported(
                f"Detected OS {machine!r} ❌ - this script is strictly built for MacOS (darwin) only."
            )
        
        mac_version = tuple(int(v) for v in self.mac_version.split(".")[:2])
        if mac_version < self.MINIMUM_COMPATIBLE_VERSION:
            version_string = "{}.{}".format
            detected = version_string(*mac_version)
            required = version_string(*self.MINIMUM_COMPATIBLE_VERSION)
            raise MachineNotSupported(
                f"idleDetector cannot run on this machine."
                f"\nDetected macOS version: {detected} ❌"
                f"\nMinimum required version: {required} (Mac OS X 10.8 or higher)."
            )
    
    @property
    def mac_version(self):
        return get_mac_version()[0]
    
    @property
    def hostname(self):
        return get_nodename().removesuffix(".local")
    
    @property
    def username(self):
        return get_env("USER") or get_env("LOGNAME")
