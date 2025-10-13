import asyncio
from dataclasses import dataclass, field
from typing import Optional

from ..utils.common import DISPLAY_WAS_OFF, validate_interval_value
from ._dataclasses import Serializable, idleStages
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
    display_was_off: bool = field(default=DISPLAY_WAS_OFF, init=False)

    async def get_machines_available_stages(
        self, screensaver_mode=None, display_off_mode=None
    ):
        """
        Determine which idle stages are valid for the current configuration.
        The returned stage set depends on which idle control modes (screensaver/display off)
        are currently configured on the system.
        """
        if screensaver_mode and display_off_mode:
            return idleStages.idle_mode_stages()
        elif display_off_mode:
            return idleStages.display_off_stages()
        elif screensaver_mode:
            return idleStages.screensaver_mode_stages()
        # Fallback when no modes are explicitly set
        return idleStages.idle_only_stages()

    async def determine_current_stage(
        self,
        idle_interval: Optional[int | float] = None,
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
        seconds = idle_seconds_obj.seconds

        # Ensure display mode states are updated according to retrieved system info
        await machine.check_display_modes(screensaver_time, display_off_time)

        # --- Establish baseline stage if not yet set ---
        # Ensures a deterministic state before applying advanced mode logic.
        if self.idle_stage is None:
            self.idle_stage = (
                idleStages.USER_IDLE
                if idle_seconds_obj.is_idle()
                else idleStages.USER_ACTIVE
            )

        # --- Transition from display-off to wake-up ---
        # If display was off and user activity resumes, emit a WAKE_UP transition once.
        if DISPLAY_WAS_OFF and not idle_seconds_obj.is_idle():
            self.idle_stage = idleStages.WAKE_UP
            self.display_was_off = DISPLAY_WAS_OFF = False
            return

        # --- Determine available stages based on machine configuration ---
        has_sleep_mode, has_display_off_mode = await asyncio.gather(
            machine.has_sleep_mode(), machine.has_display_off_mode()
        )
        modes_are_set = await machine.modes_are_set()

        # --- PRIORITY: Determine available stages based on system config ---
        # Only stages relevant to the current machine configuration are considered.
        available_stages = await self.get_machines_available_stages(
            has_sleep_mode, has_display_off_mode
        )

        # --- Idle interval logic ---
        # If no modes are set and an idle interval is provided, it takes precedence.
        # This allows users to enforce a specific idle detection behavior even
        # when the system has no screensaver or display-off timeouts configured.
        # However, if modes are set, the system's configured times take priority
        # over any provided idle interval.
        reference_interval = (
            idle_interval
            if validate_interval_value(idle_interval, default=None)
            and not modes_are_set
            else None
        )

        # --- Screensaver/display-off interpretation ---
        # If the user opts to treat the screensaver as equivalent to the display being off,
        # and the machine has a screensaver mode configured, then the display-off logic
        # applies when evaluating stages that depend on the display being off.
        # This is relevant for stages like DISPLAY_OFF and SCREEN_SAVER.
        # NOTE: This setting is ignored if the machine lacks a screensaver mode.
        display_is_considered_off = all(
            (consider_screensaver_as_off, machine.has_sleep_mode)
        )

        # --- Final stage resolution loop ---
        # For each candidate idle stage, check if the current idle time exceeds its threshold.
        # The first stage that qualifies sets the machine’s current idle stage.
        for idle_stage in available_stages:
            # Initialize the reference_seconds to the user-provided idle interval, if any.
            # This value will be used to compare against the thresholds for each idle stage.
            reference_seconds = reference_interval

            # If no user-provided interval is available, determine the reference time
            # based on the type of idle stage being evaluated.
            # For display-off stages, use the system's display-off timeout.
            if reference_seconds is None:
                if display_off_time and idleStages.is_display_off_stage(idle_stage):
                    reference_seconds = display_off_time
                # For screensaver stages, use the system's screensaver timeout.
                elif screensaver_time and idleStages.is_screensaver_stage(idle_stage):
                    reference_seconds = screensaver_time

            # If no valid reference time could be determined for the current stage,
            # skip this stage and move to the next one in the list.
            if reference_seconds is None:
                continue

            # Each idle stage defines its own relative threshold; use the reference_seconds
            # (e.g., display off or sleep delay) to scale its threshold dynamically.
            if seconds > idle_stage.threshold(reference_seconds):
                self.idle_stage = idle_stage

                # NOTE (important):
                # Assess whether the display should be considered off.
                # This determination is relevant only for specific stages
                # such as DISPLAY_OFF or SCREEN_SAVER.
                # If the display is physically off, or if the screensaver is active
                # and configured to be treated as equivalent to the display being off,
                # update the state to reflect that the display is off.
                display_turned_off = await machine.display_is_turned_off()
                if display_turned_off or all(
                    (
                        # Avoid relying on `machine.modes_are_set` here, as its behavior
                        # can vary depending on the user's system configuration settings
                        # during this stage of processing.
                        display_is_considered_off,
                        idle_stage
                        in idleStages.display_off_stages(display_is_considered_off),
                    )
                ):
                    self.idle_stage = idle_stage
                    self.display_was_off = DISPLAY_WAS_OFF = True
