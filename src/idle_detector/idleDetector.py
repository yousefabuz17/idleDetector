import asyncio
import signal
from typing import Optional

from .models.stage_manager import StageManager
from .utils.common import (
    DEFAULT_START_TIME_INTERVAL,
    IDLE_DETECTOR_RUN,
    validate_interval_value,
)


class idleDetector:
    """
    Asynchronous controller for monitoring and managing macOS system idle states.

    This class continuously evaluates system activity through the associated
    `StageManager`, leveraging macOS-level metrics (screensaver, display state,
    idle duration) to classify user inactivity stages in real time.

    It supports graceful termination via system signals and provides a configurable
    polling interval for the idle detection loop.
    """

    def __init__(
        self,
        machine,
        start_time_interval: int | float = DEFAULT_START_TIME_INTERVAL,
        ignoreDND: Optional[bool] = True,
    ):
        self.machine = machine
        self._start_time_interval = start_time_interval
        self._ignore_dnd = ignoreDND

        self.__signal_started = False

    async def __aenter__(self):
        """Initialize the asynchronous context by preparing signal handlers."""
        await self.setup_signal_handlers()
        return self

    async def __aexit__(self, *args, **kwargs):
        """
        Cleanup routine executed upon exiting the asynchronous context manager.
        Ensures that idle detection is cleanly terminated.
        """
        self.shutdown_idle_detection(*args, **kwargs)

    async def initialize_run(self):
        """
        Initialize global run state for the idle detection loop.

        Sets the internal control flag that governs whether the main loop
        continues executing. This is invoked once at startup.
        """
        global IDLE_DETECTOR_RUN
        IDLE_DETECTOR_RUN = True

    async def assign_signal_handler(self, handler):
        """
        Assign asynchronous signal handlers for graceful shutdown.

        Args:
            handler (Callable): Function or coroutine invoked upon receiving
                a termination or interrupt signal.
        """
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGTERM, handler)
        loop.add_signal_handler(signal.SIGINT, handler)

    async def setup_signal_handlers(self):
        """
        Initialize signal handlers for process termination and interruption.

        This method ensures signal handlers are registered only once per process
        to prevent redundant or conflicting registrations.
        """
        if not self.__signal_started:
            await self.assign_signal_handler(self.shutdown_idle_detection)
            self.__signal_started = True

    def shutdown_idle_detection(self, *args, **kwargs):
        """
        Gracefully terminate the idle detection loop.

        This method clears the global run flag used by the detection loop,
        allowing any ongoing asynchronous iteration to complete before exiting.
        """
        global IDLE_DETECTOR_RUN
        IDLE_DETECTOR_RUN = False

    async def start_idle_detection(
        self,
        idle_interval_if_no_modes_are_set: Optional[int | float] = None,
        *,
        consider_screensaver_as_off: Optional[bool] = False,
    ):
        """
        Begin the asynchronous idle detection process.

        This method continuously monitors system activity and determines the
        current idle state using the associated `StageManager`. It operates
        in an event-driven loop that remains active until a termination signal
        (SIGINT or SIGTERM) is received, allowing for continuous background
        idle tracking.

        Args:
            idle_interval_if_no_modes_are_set (Optional[int | float]):
                A user-defined fallback idle interval (in seconds) used when
                the machine lacks both display-sleep and sleep-mode configurations.
                This parameter ensures that idle detection remains functional
                even on systems without native idle triggers.

                Specifically:
                - If the operating system provides no hardware or OS-level
                  indication of idle transitions (e.g., no display-off or sleep
                  state is configured), the detector uses this interval as a
                  threshold to infer idleness.
                - The system will consider the user "idle" once the elapsed
                  inactive time surpasses this defined value.
                - When provided, this interval effectively replaces automatic
                  detection mechanisms that depend on power or display state.

                Example:
                    If `idle_interval_if_no_modes_are_set=300`, the system
                    will treat the user as idle after 300 seconds (5 minutes)
                    of inactivity, even if no sleep or display-off modes exist.

            consider_screensaver_as_off (Optional[bool]):
                Indicates whether to treat the screensaver state as equivalent
                to the display being off. Defaults to False. When set to True,
                screensaver activation will be interpreted as display-off for
                idle classification.

        Notes:
            - The detection loop runs indefinitely until explicitly terminated
              via signal handling.
            - Idle state evaluation and stage updates are managed through
              `StageManager.determine_current_stage()`.
            - The polling frequency between evaluations is determined by
              the validated start interval or the user-defined fallback.
            - This method leverages non-blocking sleep to maintain event loop
              responsiveness during idle monitoring.
        """

        # Validate and normalize the startup delay interval.
        # This defines the time to wait (if enabled) before the first idle check.
        start_time_interval = validate_interval_value(self._start_time_interval)

        # Optionally allow the system to stabilize before the first state evaluation.
        # await asyncio.sleep(start_time_interval)

        # Initialize core components responsible for controlling runtime state.
        # This ensures global flags and signal handlers are ready before entering the loop.
        await asyncio.gather(self.initialize_run(), self.setup_signal_handlers())

        # Begin the main idle detection loop.
        # This loop runs indefinitely until the global flag is toggled off by a shutdown signal.
        while IDLE_DETECTOR_RUN:
            machine = self.machine
            stage_manager = StageManager(machine)

            # Evaluate the current system state and determine which idle stage applies.
            # The StageManager encapsulates logic for:
            #   - Interpreting display/sleep activity.
            #   - Applying the user-defined fallback idle interval when no native modes exist.
            #   - Updating `idle_stage` (e.g., active, idle, screensaver, display_off, etc)
            #     and tracking total idle seconds.
            await stage_manager.determine_current_stage(
                idle_interval_if_no_modes_are_set, consider_screensaver_as_off
            )
            print(
                stage_manager.idle_stage,
                stage_manager.idle_seconds,
                stage_manager.display_was_off,
            )
