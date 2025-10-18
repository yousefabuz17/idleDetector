import asyncio
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Optional

from ..utils.common import DISPLAY_WAS_OFF, validate_interval_value
from ._dataclasses import Serializable, SerializedNamespace, idleStages
from .machine import MacOS
from .time_handler import idleSeconds


@dataclass(
    eq=False,
    match_args=False,
    unsafe_hash=True,
    slots=True,
    weakref_slot=True,
)
class StageManager(Serializable):
    """
    Determines the current idle stage of a Mac machine based on system activity,
    screen state, and time thresholds. Integrates system-derived idle metrics
    with configurable thresholds for each stage (user idle, screensaver, display off, etc.).
    """

    machine: MacOS
    idle_seconds: idleSeconds = field(default=None, init=False)
    idle_stage: idleStages = field(default=None, init=False)
    available_idle_stages: Iterable[idleStages] = field(
        default_factory=list, init=False
    )
    display_was_off: bool = field(default=DISPLAY_WAS_OFF, init=False)
    total_seconds_before_waking_up: Optional[float] = field(default=None, init=False)
    reference_timers: Optional[SerializedNamespace] = field(default=None, init=False)

    def get_machines_available_stages(
        self, screensaver_mode=None, display_off_mode=None
    ):
        """
        Determine which idle stages are valid for the current configuration.
        The returned stage set depends on which idle control modes (screensaver/display off)
        are currently configured on the system.
        """
        if screensaver_mode and display_off_mode:
            stages = idleStages.idle_mode_stages()
        elif display_off_mode:
            stages = idleStages.display_off_stages()
        elif screensaver_mode:
            stages = idleStages.screensaver_mode_stages()
        else:
            # Fallback when no modes are explicitly set
            stages = idleStages.idle_only_stages()

        return stages

    def update_reference_timer(
        self, screensaver_time, display_off_time, reference_interval
    ):
        self.reference_timers = SerializedNamespace(module="ReferenceTimers")
        self.reference_timers.screensaver_time = screensaver_time
        self.reference_timers.display_off_time = display_off_time
        self.reference_timers.reference_interval = reference_interval

    def update_display_off_stage(self, total_seconds_before_waking_up, idle_stage):
        global DISPLAY_WAS_OFF

        # Preserve the last-known idle seconds while the display goes off.
        # This snapshot will be used later for the single wake-up transition.
        # Keep it updated each poll while the display remains off.
        self.total_seconds_before_waking_up = total_seconds_before_waking_up
        self.idle_stage = idle_stage
        self.display_was_off = DISPLAY_WAS_OFF = True

    async def detect_current_stage(
        self,
        idle_interval_if_no_modes_are_set: Optional[int | float] = None,
        consider_screensaver_as_off: Optional[bool] = False,
    ):
        global DISPLAY_WAS_OFF
        machine = self.machine

        # --- Fetch machine metrics concurrently ---
        idle_seconds_obj, display_off_time, screensaver_time = await asyncio.gather(
            machine.current_idle_time(),
            machine.get_display_off_time(),
            machine.get_screensaver_time(),
        )

        # Capture the latest measured idle time from the machine
        self.idle_seconds = idle_seconds_obj
        machine_is_idle = idle_seconds_obj.is_idle()
        seconds = self.idle_seconds.seconds

        # Ensure display mode states are updated according to retrieved system info
        await machine.check_display_modes(screensaver_time, display_off_time)

        # --- Establish baseline stage if not yet set ---
        # Ensures a deterministic state before applying advanced mode logic.
        self.idle_stage = (
            idleStages.USER_IDLE if machine_is_idle else idleStages.USER_ACTIVE
        )

        # --- Transition from display-off to wake-up ---
        # When the system previously recorded that the display was off (DISPLAY_WAS_OFF),
        # we only need to observe a single change from idle → active to emit a wake event.
        # This branch performs that one-time transition and preserves the last-known
        # idle duration so callers can reason about how long the system was idle before wake.
        if DISPLAY_WAS_OFF and not machine_is_idle:
            # If the machine is no longer considered idle.
            # Flip the global flag so this path will not re-fire until a new display-off
            # event is observed; set the stage to WAKE_UP and return immediately so the
            # caller sees the wake transition before any further stage processing.
            DISPLAY_WAS_OFF = False
            self.idle_stage = idleStages.WAKE_UP
            return

        # --- Determine available stages based on machine configuration ---
        (
            has_sleep_mode,
            has_display_off_mode,
            modes_are_set,
        ) = await asyncio.gather(
            machine.has_sleep_mode(),
            machine.has_display_off_mode(),
            machine.modes_are_set(verify_both_are_set=False),
        )

        # --- Idle interval logic ---
        # If no modes are set and an idle interval is provided, it takes precedence.
        # This allows users to enforce a specific idle detection behavior even
        # when the system has no screensaver or display-off timeouts configured.
        # However, if modes are set, the system's configured times take priority
        # over any provided idle interval.
        reference_interval = user_set_custom_idle_interval = (
            idle_interval_if_no_modes_are_set
            if validate_interval_value(idle_interval_if_no_modes_are_set)
            and not modes_are_set
            else None
        )

        self.update_reference_timer(
            screensaver_time, display_off_time, reference_interval
        )

        if not self.reference_timers.has_arguments():
            # If no display timers nor a custom interval
            # is set. Simply stick with USER_IDLE and USER_ACTIVE
            # stages.
            # NOTE: Settings (display-times) can be updated/configured in real-time
            await asyncio.sleep(3)
            return

        # --- PRIORITY: Determine available stages based on system config ---
        # Only stages relevant to the current machine configuration are considered.
        self.available_idle_stages = self.get_machines_available_stages(
            has_sleep_mode, has_display_off_mode
        )

        # --- Screensaver/display-off interpretation ---
        # If the user opts to treat the screensaver as equivalent to the display being off,
        # and the machine has a screensaver mode configured, then the display-off logic
        # applies when evaluating stages that depend on the display being off.
        # This is relevant for stages like DISPLAY_OFF and SCREEN_SAVER.
        # NOTE: This setting is ignored if the machine lacks a screensaver mode.
        display_is_considered_off = all((consider_screensaver_as_off, has_sleep_mode))

        # NOTE (important):
        # Assess whether the display should be considered off.
        # This determination is relevant only for specific stages
        # such as DISPLAY_OFF or SCREEN_SAVER.
        # If the display is physically off, or if the screensaver is active
        # and configured to be treated as equivalent to the display being off,
        # update the state to reflect that the display is off.
        screensaver_is_running, display_turned_off = await asyncio.gather(
            machine.screensaver_is_active(), machine.display_is_turned_off()
        )
        is_display_off = any(
            (screensaver_is_running, display_turned_off, display_is_considered_off)
        )

        # --- Final stage resolution loop ---
        # For each candidate idle stage, check if the current idle time exceeds its threshold.
        # The first stage that qualifies sets the machine’s current idle stage.
        for idle_stage in self.available_idle_stages:
            # Initialize the reference_seconds to the user-provided idle interval, if any.
            # This value will be used to compare against the thresholds for each idle stage.
            reference_seconds = reference_interval

            # If no user-provided interval is available, determine the reference time
            # based on the type of idle stage being evaluated.
            if reference_seconds is None:
                # For display-off stages, use the system's display-off timeout.
                if display_off_time and idle_stage.is_display_off_stage():
                    reference_seconds = display_off_time
                # For screensaver stages, use the system's screensaver timeout.
                elif screensaver_time and idle_stage.is_screensaver_stage():
                    reference_seconds = screensaver_time
                else:
                    # If no valid reference time is available, exit the loop early.
                    # This can happen if the system lacks both display-off and screensaver modes,
                    # and no user-defined idle interval is provided. In such cases, only the
                    # USER_ACTIVE and USER_IDLE stages are applicable, which would have already
                    # been handled during the initial stage setup.
                    # NOTE:
                    # Since the idle interval can be configured dynamically at runtime, this check
                    # ensures that only stages with valid thresholds are processed, avoiding
                    # unnecessary iterations.
                    break

            # Each idle stage specifies its own relative threshold, which is dynamically
            # scaled based on the reference_seconds (e.g., display-off or sleep timeout).
            # NOTE:
            # If a stage does not have a valid threshold within the available options,
            # the original reference value will be used as-is.
            if is_display_off or seconds > idle_stage.threshold(reference_seconds):
                self.idle_stage = idle_stage
                args = None

                # Avoid relying on `machine.modes_are_set` here, as its behavior
                # can vary depending on the user's system configuration settings
                # during this stage of processing.

                if user_set_custom_idle_interval:
                    # Since the user has provided a custom idle interval,
                    # the system will default to the `USER_IDLE` stage during
                    # the idle period. This ensures that the idle detection
                    # logic respects the user-defined interval, even if the
                    # system's native modes (e.g., screensaver or display-off)
                    # are not configured. Once the system transitions out of
                    # the idle state, the `WAKE_UP` stage will be triggered
                    # to signify the end of the idle period.
                    args = (seconds, idleStages.USER_IDLE)
                else:
                    # Avoid relying on `machine.modes_are_set` here, as its behavior
                    # can vary depending on the user's system configuration settings
                    # during this stage of processing.
                    is_stage_after_screensaver = idle_stage >= idleStages.SCREENSAVER
                    if is_stage_after_screensaver and is_display_off:
                        args = (seconds, idle_stage)

                if args is not None:
                    self.update_display_off_stage(*args)
                    await asyncio.sleep(1)
                    break
