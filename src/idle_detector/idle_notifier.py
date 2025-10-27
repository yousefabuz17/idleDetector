import asyncio
from functools import partial
from operator import sub
from typing import Optional

from .models import (
    idleSeconds,
    idleStages,
)
from .utils.common import reverse_sort


class idleNotifier:
    def __init__(self, idle_detector):
        self._idle_detector = idle_detector

    def calculate_display_time_difference(self):
        idle_detector = self._idle_detector
        reference_timers = idle_detector.stage_manager.reference_timers
        display_off_time = reference_timers.display_off_time
        screensaver_time = reference_timers.screensaver_time
        reference_interval = reference_timers.reference_interval

        # Determine which two timers are relevant for computing a delta.
        # The logic intentionally avoids explicit branching semantics; instead,
        # it selects the first matching pair of configured timing modes, providing
        # flexibility for systems that may expose partial idle-mode configurations.
        if all(modes := (display_off_time, screensaver_time)):
            pass
        elif all(modes := (reference_interval, display_off_time)):
            pass
        elif all(modes := (reference_interval, screensaver_time)):
            pass
        else:
            modes = None

        # If valid timing data exists, compute the temporal offset between the two.
        # The resulting difference is returned in a human-readable format suitable
        # for user-facing notifications or debug traces.
        if modes:
            idle_seconds = idleSeconds(sub(*reverse_sort(modes)))
            human_readable_duration = idle_seconds.human_readable(
                idle_detector.compact_timestamp
            )
            return human_readable_duration

    def create_idle_time_message(
        self, duration, compact_timestamp, message_only: bool = True
    ):
        # Create a concise descriptor for how long the system has been idle.
        # Converts raw duration seconds into a normalized, human-readable value.
        seconds_duration = idleSeconds(duration)
        hr_format = seconds_duration.human_readable(compact_name=compact_timestamp)
        msg = f"Machine been idle for {hr_format}."

        if message_only:
            return msg
        return seconds_duration.seconds, msg

    def create_message_template(
        self,
        prefix: str = "",
        time_left_until_next_display_stage=None,
        *,
        pre_screensaver_stage: bool = False,
        sleep_time: bool = False,
    ):
        # Produces a context-aware message string depending on the
        # next stage and user-defined prefix. The logic gracefully
        # adapts between pre-screensaver, display-off, and generic states.
        duration = time_left_until_next_display_stage or "soon"

        if pre_screensaver_stage:
            msg = f"Screensaver will activate in {duration}"
        elif sleep_time:
            msg = f"Display will fully turn off in {duration}"
        else:
            msg = ""

        # Streamline message when the duration is immediate.
        # This removes redundant linguistic fillers (e.g., "in soon").
        if duration == "soon":
            msg = msg.replace("in ", "", 1) + "."

        return "{}{}{}".format(prefix, " " if prefix else "", msg)

    def build_notification_message(self):
        stage_manager = self._idle_detector.stage_manager
        idle_stage = stage_manager.idle_stage
        idle_seconds = stage_manager.idle_seconds
        seconds = idle_seconds.seconds
        compact_timestamp: bool = self._idle_detector.compact_timestamp

        reference_timers = stage_manager.reference_timers
        reference_time = (
            reference_timers.display_off_time
            if idle_stage in idleStages.display_off_only_stages()
            else reference_timers.screensaver_time
        )

        # Compute remaining time until the next major idle transition stage.
        # This enables proactive notifications (e.g., before display off or sleep).
        if reference_time:
            next_stage_duration_remaining = reference_time - seconds
            idle_seconds_time_left = idleSeconds(next_stage_duration_remaining)
            time_left_until_next_display_stage = idle_seconds_time_left.human_readable(
                compact_name=compact_timestamp
            )
        else:
            time_left_until_next_display_stage = None

        prefix = self.create_idle_time_message(seconds, compact_timestamp)

        # Dynamically format the outgoing message template based on the current stage.
        # Each branch corresponds to a specific user-facing idle milestone.
        match idle_stage:
            case idleStages.HALFWAY_TO_SCREENSAVER:
                return self.create_message_template(
                    prefix,
                    time_left_until_next_display_stage,
                    pre_screensaver_stage=True,
                )
            case idleStages.THREE_QUARTERS_TO_SCREENSAVER:
                return self.create_message_template(
                    prefix,
                    time_left_until_next_display_stage,
                    pre_screensaver_stage=True,
                )
            case idleStages.SCREENSAVER:
                next_stage_duration = self.calculate_display_time_difference()

                if next_stage_duration is not None:
                    time_left_until_next_display_stage = next_stage_duration

                return self.create_message_template(
                    "Snooze time 💤.",
                    time_left_until_next_display_stage,
                    sleep_time=True,
                )
            case idleStages.DISPLAY_OFF_WARNING:
                return self.create_message_template(
                    "Sleep time 💤.", None, sleep_time=True
                )
            case idleStages.WAKE_UP:
                total_seconds_before_waking_up = (
                    stage_manager.total_seconds_before_waking_up
                )
                seconds, prefix = self.create_idle_time_message(
                    total_seconds_before_waking_up,
                    compact_timestamp,
                    message_only=False,
                )
                return f"{prefix}\nTotal Seconds: {int(seconds):,}"
            case _:
                # Fallback: minimal descriptor (no contextual expansion).
                return prefix

    async def send_alert(self):
        idle_detector = self._idle_detector
        idle_stage = idle_detector.stage_manager.idle_stage
        terminal_notifier = idle_detector.terminal_notifier
        content_images = terminal_notifier.content_images
        message = self.build_notification_message()

        # --- Notification grouping semantics ---
        # The 'group' key in the terminal-notifier payload must be **omitted entirely**
        # unless grouping is explicitly enabled. Passing a None or falsy group ID still
        # results in terminal-notifier generating an implicit group hash, which merges
        # unrelated notifications together.
        #
        # To avoid this unintended aggregation, we construct the kwargs dynamically:
        # - when grouping is enabled → provide {'group': group_type_id}
        # - when disabled → provide an empty dict, ensuring no 'group' field exists
        #
        # This subtle behavior prevents "phantom grouping" side effects that occur when
        # notifications share an unset but internally normalized group identifier.
        group_type_id = idle_stage.stage_group_id()
        group = {"group": group_type_id} if idle_detector.group_notifications else {}

        # Compose the notifier payload. Each argument corresponds to a display
        # attribute within the terminal-notifier integration. The mapping uses
        # symbolic accessors (content_images, ignoreDnD) to remain adaptable
        # across desktop environments.
        kwarg_cmd = dict(
            title="IDLE-DETECTION",
            subtitle=idle_stage.stage_name(),
            message=message,
            ignoreDnD=idle_detector.ignoreDnD,
            contentImage=group_type_id.content_image_by_group(content_images),
            **group,
        )

        # Delegate final notification dispatch asynchronously to the terminal notifier.
        await terminal_notifier.notify(**kwarg_cmd)
