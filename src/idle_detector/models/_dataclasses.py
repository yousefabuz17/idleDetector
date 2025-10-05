from enum import IntEnum, StrEnum, auto
from operator import mul, sub



class GroupTypes(StrEnum):
    IDLE = auto()
    SLEEP_TIME = auto()
    DISPLAY_OFF = auto()



class NotifierFlags(StrEnum):
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
    APPICON = "appIcon"
    CONTENTIMAGE = "contentImage"
    IGNOREDND = "ignoreDND"
    
    @classmethod
    def is_flag_available(cls, flag: str):
        return flag.removeprefix("-") in cls
    
    @property
    def flag(self):
        return "-" + self.value
    
    
    
class TimeTypes(IntEnum):
    DAYS = 86400
    HOURS = 3600
    MINUTES = 60
    SECONDS = 1

    def divmod(self, seconds):
        return divmod(seconds, self.value)

    def compact_name(self):
        return self.name.lower()[0]

    def format_time_value(self, value, compact_name: bool = True, title_case=False):
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




class idleStages(StrEnum):
    HALFWAY_FROM_SCREENSAVER = auto()
    THIRD_QUARTERS_FROM_SCREENSAVER = auto()
    SCREENSAVER = auto()
    DISPLAY_OFF_WARNING = auto()
    
    def threshold(self, seconds):
        op_method = mul
        match self:
            case idleStages.HALFWAY_FROM_SCREENSAVER:
                threshold = 2
            case idleStages.THIRD_QUARTERS_FROM_SCREENSAVER:
                threshold = 0.75
            case idleStages.DISPLAY_OFF_WARNING:
                threshold = 10
                op_method = sub
            case _:
                op_method = None
                threshold = seconds
        if op_method:
            return op_method(seconds, threshold)
        return threshold


print(idleStages.DISPLAY_OFF_WARNING.threshold(100))