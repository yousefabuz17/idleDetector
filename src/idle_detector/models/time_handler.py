from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from functools import total_ordering
from typing import ClassVar

from ..utils.common import IS_IDLE_START_TIME, to_seconds
from ._dataclasses import TimeTypes


@total_ordering
@dataclass(
    eq=False,
    frozen=True,
    match_args=False,
    unsafe_hash=True,
    slots=True,
    weakref_slot=True,
)
class idleSeconds:
    """
    Immutable, type-safe representation of system idle duration in seconds.

    Encapsulates raw time values (float or Decimal) into a strongly-typed object
    that integrates with the idle-state detection and timing subsystems. Supports
    arithmetic-safe comparison, timedelta conversion, and readable formatting for
    logging or user interfaces.

    Attributes:
        seconds (Decimal | float):
            The duration of system idleness, stored as a numeric second value.

    Class Variables:
        to_seconds (staticmethod):
            Shared conversion utility to normalize numeric values into seconds,
            imported from the common utility module.

    Comparison Behavior:
        Instances can be compared directly against other `idleSeconds` objects or
        numeric values (`int`, `float`). Comparisons use the normalized second value
        to ensure consistency across numeric types.

    Methods:
        - __str__():
            Return the normalized second value as a string.
        - __lt__(other):
            Compare two idle durations by seconds.
        - __eq__(other):
            Equality comparison by normalized seconds.
        - from_seconds(seconds: float) → idleSeconds:
            Factory constructor for creating instances from raw numeric values.
        - is_idle() → bool:
            Determine whether the current idle duration meets or exceeds the
            configured system idle threshold (`IS_IDLE_START_TIME`).
        - asdelta() → timedelta:
            Convert the internal second value into a `datetime.timedelta` object.
        - human_readable(compact_name: bool = False) → str:
            Convert seconds into a human-readable time format.
            Examples:
                - `3675s → "1h 1m 15s"`
                - `3675s → "1 hour 1 minute 15 seconds"` (if `compact_name=False`)

    Example:
        >>> idleSeconds.from_seconds(125).human_readable()
        '2m 5s'
        >>> idleSeconds(3600).asdelta()
        datetime.timedelta(seconds=3600)
        >>> idleSeconds(Decimal("300")).is_idle()
        True

    Designed for:
        Consistent, safe handling of idle-time durations in automation,
        monitoring, or user activity tracking frameworks, ensuring uniform
        comparison and formatted reporting across system components.
    """

    seconds: Decimal | float

    # Shared conversion helper across instances; avoids rebinding per object.
    to_seconds: ClassVar = staticmethod(to_seconds)

    def __str__(self):
        return f"{self.to_seconds(self.seconds)}"

    def __lt__(self, other):
        if not isinstance(other, (idleSeconds, int, float)):
            return NotImplemented
        return self.to_seconds(self.seconds) < self.to_seconds(other)

    def __eq__(self, other):
        if not isinstance(other, (idleSeconds, int, float)):
            return NotImplemented
        return self.to_seconds(self.seconds) == self.to_seconds(other)

    @classmethod
    def from_seconds(cls, seconds: float):
        """Factory for creating idleSeconds from a numeric literal."""
        return idleSeconds(cls.to_seconds(seconds))

    def is_idle(self):
        """
        Check if the systems current idle duration meets or exceeds the system’s configured idle threshold.
        """
        return self.seconds >= IS_IDLE_START_TIME

    def asdelta(self):
        """Convert seconds into a timedelta object"""
        return timedelta(seconds=self.seconds)

    def human_readable(self, compact_name=False):
        """
        Convert seconds into a structured human-readable time string.
        Example: 3675s → "1h 1m 15s" or "1 hour 1 minute 15 seconds"
        """
        total_seconds = int(self.seconds)

        # Clamp negatives to zero to avoid invalid time display
        if total_seconds < 0:
            total_seconds = 0

        # Zero duration → return immediate unit (e.g., "0s" or "0 seconds")
        if total_seconds == 0:
            return TimeTypes.SECONDS.format_time_value(
                total_seconds, compact_name=compact_name
            )

        # Break total seconds into (days, hours, minutes, seconds)
        days, remainder = TimeTypes.DAYS.divmod(total_seconds)
        hours, remainder = TimeTypes.HOURS.divmod(remainder)
        minutes, seconds = TimeTypes.MINUTES.divmod(remainder)

        # Only include non-zero components; zip aligns each numeric with its TimeType
        time_parts = [
            t_type.format_time_value(num, compact_name=compact_name)
            for num, t_type in zip(
                (days, hours, minutes, seconds), TimeTypes, strict=True
            )
            if num > 0
        ]

        # Final string composition: "1h 2m 5s" or "1 hour 2 minutes 5 seconds"
        return " ".join(time_parts)
