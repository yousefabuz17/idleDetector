import asyncio
import signal
from dataclasses import dataclass, field
from typing import Optional

from .idle_notifier import idleNotifier
from .models import idleStages, MacOS, Serializable, StageManager, TerminalNotifier
from .utils.common import (
    DEFAULT_START_TIME_INTERVAL,
    IDLE_DETECTOR_RUN,
    validate_interval_value,
)


@dataclass(
    kw_only=True,
    unsafe_hash=True,
    match_args=False,
    slots=True,
    weakref_slot=True,
)
class idleDetector(Serializable):
    """
    Asynchronous controller for monitoring and managing macOS system idle states.

    This class continuously evaluates system activity through the associated
    `StageManager`, leveraging macOS-level metrics (screensaver, display state,
    idle duration) to classify user inactivity stages in real time.

    It supports graceful termination via system signals and provides a configurable
    polling interval for the idle detection loop.
    """

    machine: MacOS = field(kw_only=False)
    ignoreDnD: Optional[bool] = field(default=True)
    compact_timestamp: Optional[bool] = field(default=False)
    sleep_time_interval: int | float = field(default=DEFAULT_START_TIME_INTERVAL)
    idle_interval_if_no_modes_are_set: Optional[int | float] = field(default=None)
    consider_screensaver_as_off: Optional[bool] = field(default=False)
    group_notifications: Optional[bool] = field(default=False)

    def __post_init__(self):
        self.__signal_started = False
        self.__stage_manager = None
        self.__terminal_notifier = None
        self.__idle_notifier = None
        self.__stages_notifier = None

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

    async def initialize_notifiers(self):
        """
        Initialize the notifiers for idle detection.

        This method ensures that the `TerminalNotifier` is properly instantiated
        and verified for use. Additionally, it initializes the `idleNotifier`
        if the `TerminalNotifier` is successfully set up.
        """
        if self.__terminal_notifier is None:
            self.__terminal_notifier = terminal_notifier = TerminalNotifier()
            await terminal_notifier.check_notifier()

        if self.__idle_notifier is None:
            self.__idle_notifier = idleNotifier(self)

        if self.__stages_notifier is None:
            self.__stages_notifier = idleStages.notifier_stages()

    async def initialize_stage_manager(self):
        if self.__stage_manager is None:
            self.__stage_manager = StageManager(self.machine)

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

    async def start_idle_detection(self):
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
              `StageManager.detect_current_stage()`.
            - The polling frequency between evaluations is determined by
              the validated start interval or the user-defined fallback.
            - This method leverages non-blocking sleep to maintain event loop
              responsiveness during idle monitoring.
        """

        # Validate and normalize the startup delay interval.
        # This defines the time to wait (if enabled) before the first idle check.
        sleep_time_interval = validate_interval_value(self.sleep_time_interval)

        # Initialize core components responsible for controlling runtime state.
        # This ensures global flags, and signal handlers, are ready before entering the loop.
        # NOTE: These operations are asynchronous and may involve I/O or system calls
        # and must complete before the main loop begins.
        await asyncio.gather(
            self.initialize_run(),
            self.setup_signal_handlers(),
            self.initialize_stage_manager(),
        )

        # Begin the main idle detection loop.
        # This loop runs indefinitely until the global flag is toggled off by a shutdown signal.
        while IDLE_DETECTOR_RUN:
            # Optionally allow the system to stabilize before the first state evaluation.
            # await asyncio.sleep(sleep_time_interval)

            stage_manager = self.__stage_manager

            # Evaluate the current system state and determine which idle stage applies.
            # The StageManager encapsulates logic for:
            #   - Interpreting display/sleep activity.
            #   - Applying the user-defined fallback idle interval when no native modes exist.
            #   - Updating `idle_stage` (e.g., active, idle, screensaver, display_off, etc)
            #     and tracking total idle seconds.
            await stage_manager.detect_current_stage(
                self.idle_interval_if_no_modes_are_set, self.consider_screensaver_as_off
            )
            # await asyncio.sleep(0.1)

            # If the current stage is not configured for alerts, skip notification.
            # This prevents unnecessary notifications for benign states.
            # Stages like USER_ACTIVE or USER_IDLE typically do not trigger notifications.
            # The `is_alert_stage()` method checks if the current stage is among those
            # compatible defined in `idleStages.stages_compatible_for_alerts()`.
            alert_stage = stage_manager.idle_stage.is_alert_stage()
            if alert_stage:
                # If the stage is alert-worthy, proceed to notify.
                await self.start_terminal_notifier()
                # await asyncio.sleep(0.0001)
                print(
                    stage_manager.idle_stage,
                    stage_manager.idle_seconds,
                    stage_manager.display_was_off,
                )

            if all((
                stage_manager.idle_stage.is_non_idle_stage(),
                self.__stages_notifier is not None
            )):
                # await asyncio.sleep(1)
                self.__stages_notifier.reset_attributes()

    async def start_terminal_notifier(self):
        await self.initialize_notifiers()

        idle_notifier = self.__idle_notifier
        idle_stage = self.__stage_manager.idle_stage
        stage_notifier = self.__stages_notifier

        if not stage_notifier.stage_was_notified(idle_stage):
            await idle_notifier.send_alert()
            stage_notifier.toggle_notified_status(idle_stage)

    @property
    def terminal_notifier(self):
        return self.__terminal_notifier

    @property
    def stage_manager(self):
        return self.__stage_manager

    @property
    def idle_notifier(self):
        return self.__idle_notifier
