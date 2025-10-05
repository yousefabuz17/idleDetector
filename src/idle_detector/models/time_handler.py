from dataclasses import dataclass
from datetime import timedelta

from ._dataclasses import TimeTypes


@dataclass(
    eq=False,
    match_args=False,
    frozen=True,
    unsafe_hash=True,
    slots=True,
    weakref_slot=True,
)
class idleSeconds:
    seconds: float

    def asdelta(self):
        return timedelta(seconds=self.seconds)

    def human_readable(self, compact_name=True):
        total_seconds = abs(int(self.seconds))

        if total_seconds == 0:
            return TimeTypes.SECONDS.format_time_value(
                total_seconds, compact_name=compact_name
            )

        days, remainder = TimeTypes.DAYS.divmod(total_seconds)
        hours, remainder = TimeTypes.HOURS.divmod(remainder)
        minutes, seconds = TimeTypes.MINUTES.divmod(remainder)

        time_parts = [
            t_type.format_time_value(num, compact_name=compact_name)
            for num, t_type in zip(
                (days, hours, minutes, seconds), TimeTypes, strict=False
            )
        ]

        return " ".join(time_parts)
