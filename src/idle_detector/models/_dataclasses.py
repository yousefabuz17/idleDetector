from dataclasses import MISSING, asdict, is_dataclass
from decimal import Decimal
from enum import IntEnum, StrEnum, auto
from functools import lru_cache, total_ordering
from operator import add, mul, sub
from types import SimpleNamespace

from ..utils.common import NULL_INFINITY, reverse_sort, to_seconds, type_name


class Serializable:
    """
    Base mixin providing serialization and reset utilities for dataclass-based or
    standard class instances. Supports converting objects to dictionaries and resetting
    their fields to default values.
    """

    is_dataclass = staticmethod(is_dataclass)

    def asdict(self):
        """
        Return a serializable dictionary representation of the instance.

        - For dataclasses → uses `dataclasses.asdict`.
        - For regular classes → returns a shallow copy of `__dict__`.
        """
        if self.is_dataclass(self):
            # For dataclasses, use the built-in asdict
            return asdict(self)
        # For regular classes, use instance __dict__ (only attributes set in __init__)
        return self.__dict__.copy()

    def has_arguments(self, all_args: bool = False):
        """
        Check whether any or all attributes of the instance are truthy.

        Args:
            all_args (bool): If True, requires all attributes to be truthy.
                             If False (default), checks if any are truthy.
        """
        method = all if all_args else any
        return method(map(bool, self.asdict().values()))

    def reset_attributes(self):
        """
        Reset dataclass fields to their default or default_factory values.
        Non-dataclass instances are ignored.
        """
        if not self.is_dataclass(self):
            return

        for name, field_attr in self.__dataclass_fields__.items():
            attr_default = field_attr.default
            attr_dfactory = field_attr.default_factory

            if attr_default is MISSING and attr_dfactory:
                value = attr_dfactory()
            elif attr_default and attr_dfactory is MISSING:
                value = attr_default
            else:
                value = attr_default
            setattr(self, name, value)


class SerializedNamespace(SimpleNamespace, Serializable):
    """
    A mutable, serializable namespace with dict-like behavior and safe attribute
    resetting. Useful for runtime configuration, API responses, or ephemeral state
    containers.
    """

    def __init__(self, **kwargs):
        self.__kwargs = kwargs
        self.__name__ = kwargs.pop("module", type_name(self))
        super().__init__(**kwargs)

    @property
    def __dir__(self):
        # Exclude __name__ from dir() listings
        return [k for k in super().__dir__() if not k.startswith("_")]

    def __bool__(self):
        return bool(self.__getstate__())

    def __getstate__(self):
        # Only include public attributes for serialization
        return {k: v for k, v in super().__dict__.items() if k in self.__dir__}

    def __repr__(self):
        # Filter out __name__ from the dict before printing
        items = ("{}={!r}".format(*kv) for kv in self.__getstate__().items())
        return f"{self.__name__}({', '.join(items)})"

    def __getattribute__(self, name):
        try:
            return super().__getattribute__(name)
        except AttributeError:
            # Enables safe attribute access without exceptions
            pass

    # Dict-like interface for flexible attribute handling
    def __getitem__(self, name):
        return self.__getattribute__(name)

    def __setitem__(self, key, value):
        setattr(self, key, value)

    def __delitem__(self, key):
        if hasattr(self, key):
            delattr(self, key)

    def reset_attributes(self):
        for k, v in self.__kwargs.items():
            setattr(self, k, v)

    # Convenience methods for attribute-style dictionary access
    def get(self, key, default=None):
        return self.__getattribute__(key) or default

    def keys(self):
        return self.__getstate__().keys()

    def values(self):
        return self.__getstate__().values()

    def items(self):
        return self.__getstate__().items()

    def asdict(self):
        return self.__getstate__()


class GroupTypes(StrEnum):
    """
    Enumeration defining logical notification group categories.

    Used to classify notifications by behavioral or contextual grouping for
    scheduling, filtering, or display purposes.

    Members:
        - IDLE: Notifications related to user idle or inactivity states.
        - SLEEP_TIME: Notifications related to system or user sleep schedules.
        - DISPLAY_OFF_WARNING: Notifications triggered as a warning before the display turns off.
        - WAKE_UP: Notifications related to wake-up or resumed activity events.

    Designed for:
        Structured grouping of notifications in alerting systems, allowing
        category-based handling, suppression, or prioritization.
    """

    IDLE = auto()
    SLEEP_TIME = auto()
    DISPLAY_OFF_WARNING = auto()
    WAKE_UP = auto()

    def content_image_by_group(self, content_images: SerializedNamespace):
        return (
            content_images.wakeup_image
            if self is GroupTypes.WAKE_UP
            else content_images.idle_image
        )


class NotifierFlags(StrEnum):
    """
    Enumeration of `terminal-notifier` command-line flags with helper methods for flag handling.

    Each member corresponds to a valid argument for the macOS `terminal-notifier` utility,
    used to send local notifications from scripts or background services.

    Members:
        - HELP: Display usage information.
        - VERSION: Show the current version of terminal-notifier.
        - MESSAGE: Define the notification message body.
        - REMOVE: Remove an existing notification by group identifier.
        - LIST: List currently active notifications.
        - TITLE: Set the main notification title.
        - SUBTITLE: Set the secondary notification title.
        - SOUND: Specify a sound to play with the notification.
        - GROUP: Assign a group identifier for grouping notifications.
        - ACTIVATE: Bring a specific application to focus when the notification is clicked.
        - SENDER: Specify the application bundle identifier for the sender.
        - OPEN: Open a URL or file when the notification is clicked.
        - EXECUTE: Run a shell command when the notification is clicked.
        - APPICON: Path or name of the icon to display with the notification.
        - CONTENTIMAGE: Path to an image to embed in the notification.
        - IGNOREDND: Send notification even if “Do Not Disturb” is enabled.

    Designed for:
        Programmatic management of `terminal-notifier` arguments and safe flag validation
        when dynamically constructing macOS notification commands.
    """

    HELP = auto()
    VERSION = auto()
    MESSAGE = auto()
    REMOVE = auto()
    LIST = auto()
    TITLE = auto()
    SUBTITLE = auto()
    SOUND = auto()
    GROUP = auto()
    ACTIVATE = auto()
    SENDER = auto()
    OPEN = auto()
    EXECUTE = auto()
    APP_ICON = "appIcon"
    CONTENTIMAGE = "contentImage"
    IGNOREDND = "ignoreDnD"

    @classmethod
    def is_flag_available(cls, flag: str):
        return flag.removeprefix("-") in cls

    @property
    def flag(self):
        return "-" + self.value


class TimeTypes(IntEnum):
    """
    Enumeration of time measurement units with conversion and formatting utilities.

    Provides convenience methods for time arithmetic and string representation across
    multiple scales, used for timing, scheduling, and duration reporting.

    Members:
        - DAYS = 86400
        - HOURS = 3600
        - MINUTES = 60
        - SECONDS = 1

    Methods:
        - divmod(num):
            Return the quotient and remainder of `num` divided by the unit’s second value.
            Useful for decomposing total seconds into unit segments.
        - to_seconds(num):
            Convert a given quantity of this unit into seconds.
        - compact_name():
            Return a single-character shorthand for the unit (e.g., 'd', 'h', 'm', 's').
        - format_time_value(value, compact_name=True, title_case=False):
            Format a numeric value with its corresponding unit name.
            Examples:
                - `TimeTypes.MINUTES.format_time_value(5)` → '5m'
                - `TimeTypes.HOURS.format_time_value(1, compact_name=False)` → '1 hour'

    Designed for:
        Time-based computation, formatting, and unit conversions in system activity,
        scheduling, or logging utilities.
    """

    DAYS = 86400
    HOURS = 3600
    MINUTES = 60
    SECONDS = 1

    def divmod(self, num):
        return divmod(num, self.value)

    def to_seconds(self, num):
        return self.value * num

    def compact_name(self):
        return self.name.lower()[0]

    def format_time_value(self, value, compact_name: bool = False, title_case=False):
        if not compact_name:
            name = self.name
            sep = " "
        else:
            name = self.compact_name()
            sep = ""

        name = name.title() if title_case else name.lower()

        if value == 1:
            name = name.removesuffix("s")

        return "{}{}{}".format(value, sep, name)


@total_ordering
class idleStages(StrEnum):
    """
    Enumeration representing the progressive stages of user inactivity and system idleness.

    Each member of this enumeration corresponds to a distinct idle stage, ranging from active
    user interaction to full display sleep. The class provides utilities for threshold
    computation, stage sorting, comparison, and classification into modes such as screensaver
    or display-off.

    Stages (in ascending order of idleness):
        - USER_ACTIVE: User is fully active.
        - USER_IDLE: Initial idle state detected.
        - HALFWAY_TO_SCREENSAVER: Approximately halfway to screensaver activation.
        - THREE_QUARTERS_TO_SCREENSAVER: 75% of the way to screensaver activation.
        - SCREENSAVER: Screensaver is active.
        - DISPLAY_OFF_WARNING: Pre-display-off warning stage.
        - DISPLAY_OFF: Display has been turned off.
        - WAKE_UP: System or user has returned from an idle state.

    Internal Structures:
        - StageLevels (IntEnum):
            Numeric representations (0–7) corresponding to each stage, enabling direct
            ordering and comparison of idle progression.
        - StageNotified (dataclass):
            Tracks notification status (True/False) for each idle stage (if-applicable).
            Supports toggling and indexed access by stage enumeration.

    Comparison Behavior:
        Instances of `idleStages` can be compared directly based on their StageLevel values.
        Supports ordering operations (`<`, `>`, `==`) and `sorted()`
        to operate logically by stage order.

    Core Utility Methods:
        - threshold(reference_seconds): Compute time thresholds per stage relative to a base interval.
        - stage_name(): Return a human-readable display name for the stage.
        - stage_level(): Return the numeric level from StageLevels.
        - sort_stages(iterable): Sort an iterable of stages in logical idle order.
        - is_display_off_stage(stage): Determine if a stage represents display-off conditions.
        - is_screensaver_stage(stage): Determine if a stage is part of screensaver mode.
        - non_idle_stages(): Return [`USER_ACTIVE`, `WAKE_UP`].
        - idle_mode_stages(): Return all idle-related stages excluding non-idle ones.
        - idle_only_stages(): Return stages related to transitioning between idle and active states.
        - screensaver_mode_stages(): Return all screensaver-related stages excluding display-off.
        - display_off_stages(consider_screensaver_as_off=False): Return stages linked to display-off mode.

    Designed for:
        Structured idle-state modeling in system monitoring, automation, or user activity
        tracking frameworks where stage-based transitions need explicit ordering, logic, and
        classification.
    """

    USER_ACTIVE = auto()
    USER_IDLE = auto()
    HALFWAY_TO_SCREENSAVER = auto()
    THREE_QUARTERS_TO_SCREENSAVER = auto()
    SCREENSAVER = auto()
    DISPLAY_OFF_WARNING = auto()
    DISPLAY_OFF = auto()
    WAKE_UP = auto()

    class StageLevels(IntEnum):
        """Numeric levels for each stage to indicate order."""

        USER_ACTIVE = 0
        USER_IDLE = auto()
        HALFWAY_TO_SCREENSAVER = auto()
        THREE_QUARTERS_TO_SCREENSAVER = auto()
        SCREENSAVER = auto()
        DISPLAY_OFF_WARNING = auto()
        DISPLAY_OFF = auto()
        WAKE_UP = auto()

    class StageNotified(SerializedNamespace):
        """Track notification status for each idle stage."""

        def __getitem__(self, value: "idleStages"):
            return getattr(self, value.value)

        def get_stage(self, stage: "idleStages", *, override_self=None):
            self = override_self or self
            return getattr(self, stage.value)

        def toggle_notified_status(self, stage: "idleStages"):
            current_value = self.get_stage(stage)
            setattr(self, stage.value, not current_value)
            return self.get_stage(stage, override_self=self)

        def stage_was_notified(self, stage: "idleStages"):
            return self.get_stage(stage) is True

        @staticmethod
        def compatible_stages(cls: "idleStages"):
            return [
                cls.HALFWAY_TO_SCREENSAVER,
                cls.THREE_QUARTERS_TO_SCREENSAVER,
                cls.SCREENSAVER,
                cls.DISPLAY_OFF_WARNING,
                cls.WAKE_UP,
            ]

    def __hash__(self):
        return hash(str(self))

    def __eq__(self, value):
        if not isinstance(value, idleStages):
            return NotImplemented
        return self.stage_level() == value.stage_level()

    def __lt__(self, value):
        if not isinstance(value, idleStages):
            return NotImplemented
        return self.stage_level() < value.stage_level()

    def threshold(self, reference_seconds):
        """
        Compute the threshold duration (in seconds) for the current idle stage based on a reference time.

        This threshold determines when the system should consider the user as having reached
        a specific idle stage, relative to a reference interval (e.g., screensaver activation time).

        Stage-specific behavior:
            - `HALFWAY_TO_SCREENSAVER`:
                Threshold is 50% of the reference time.
            - `THREE_QUARTERS_TO_SCREENSAVER`:
                Threshold is 75% of the reference time.
            - `DISPLAY_OFF_WARNING`:
                Threshold is slightly less than the reference time to provide a pre-display-off warning.
                Uses 15 seconds if reference is short, otherwise 45 seconds.
            - Other stages:
                Default threshold is 0 seconds (immediate or unconditional).

        Args:
            reference_seconds (int | float | Decimal): Base interval to scale thresholds against.
                Typically derived from the system's configured screensaver or display-off delay.

        Returns:
            Decimal: Calculated threshold in seconds for the current stage.
        """
        seconds = to_seconds(reference_seconds) or NULL_INFINITY

        match self:
            case idleStages.HALFWAY_TO_SCREENSAVER:
                op_method = mul
                threshold = 0.5
            case idleStages.THREE_QUARTERS_TO_SCREENSAVER:
                op_method = mul
                threshold = 0.75
            case idleStages.SCREENSAVER:
                op_method = sub
                threshold = 5
            case idleStages.DISPLAY_OFF_WARNING:
                op_method = sub
                threshold = 15 if seconds <= TimeTypes.MINUTES else 45
            case _:
                op_method = add
                threshold = 0

        op_args = reverse_sort([seconds, Decimal(threshold)])
        return abs(op_method(*op_args)) if op_method else threshold

    def get_stage_type(self, group_ids: bool = False):
        stages = self.stages_compatible_for_alerts()

        if group_ids:
            stage_values = (GroupTypes.IDLE, *GroupTypes)
        else:
            stage_values = (
                "SleepTime Half-way Mark",
                "SleepTime Third-way Mark",
                "SleepTime Final Mark Reached",
                "🚨 Display-Off Warning 🚨",
                "Machine is Awake 🌞",
            )
        merged_values = zip(stages, stage_values)
        return next((v for s, v in merged_values if self is s), GroupTypes.IDLE)

    def stage_name(self):
        """Human-readable stage name."""
        return self.get_stage_type()

    def stage_group_id(self):
        return self.get_stage_type(group_ids=True)

    def stage_level(self):
        """Numeric level indicating the order of stages."""
        return self.StageLevels[self.name]

    @classmethod
    def sort_stages(self, iterable_of_stages):
        return sorted(iterable_of_stages, key=lambda s: s.stage_level())

    def is_display_off_stage(self):
        return self in self.display_off_only_stages()

    def is_screensaver_stage(self):
        return self in self.screensaver_mode_stages()

    def is_alert_stage(self):
        return self in self.stages_compatible_for_alerts()
    
    def is_non_idle_stage(self):
        return self in self.non_idle_stages()

    @classmethod
    def stages_compatible_for_alerts(cls):
        return cls.StageNotified.compatible_stages(cls)

    @classmethod
    @lru_cache(maxsize=1)
    def notifier_stages(cls):
        notifier_stages = cls.stages_compatible_for_alerts()
        return cls.StageNotified(**{stage: False for stage in notifier_stages})

    @classmethod
    def non_idle_stages(cls):
        """
        Stages that do not indicate user idleness.
        return [`USER_ACTIVE`, `WAKE_UP`]
        """
        return cls.sort_stages([cls.USER_ACTIVE, cls.WAKE_UP])

    @classmethod
    def idle_mode_stages(cls):
        """
        All stages except those that do not indicate user idleness.
        return all stages except [`USER_ACTIVE`, `WAKE_UP`]
        """
        return cls.sort_stages([s for s in cls if s not in cls.non_idle_stages()])

    @classmethod
    def idle_only_stages(cls):
        """
        Stages that specifically indicate user idleness when
        the user's machine does not have display-off or screensaver modes configured.
        return [`USER_ACTIVE`, `USER_IDLE`, `WAKE_UP`]
        """
        return cls.sort_stages([*cls.non_idle_stages(), cls.USER_IDLE])

    @classmethod
    def screensaver_mode_stages(cls):
        """
        Stages relevant to screensaver mode, excluding display-off related stages.
        return all stages except the last two stages [`DISPLAY_OFF_WARNING`, `DISPLAY_OFF`]
        """
        return cls.idle_mode_stages()[:-2]

    @classmethod
    def display_off_only_stages(cls):
        return cls.sort_stages([cls.DISPLAY_OFF_WARNING, cls.DISPLAY_OFF])

    @classmethod
    def display_off_stages(cls, consider_screensaver_as_off: bool = False):
        """
        Stages relevant to display-off mode, specifically the last stage.
        return [`DISPLAY_OFF`] only if `consider_screensaver_as_off` is not set.
        Otherwise, return [`SCREENSAVER`, `DISPLAY_OFF_WARNING`, `DISPLAY_OFF`]
        """
        display_off_stages = [cls.SCREENSAVER, *cls.display_off_only_stages()]
        if not consider_screensaver_as_off:
            display_off_stages = display_off_stages[-1:]
        return display_off_stages
