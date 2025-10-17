from ._version import __version__, __version_info__
from .exceptions import MachineNotSupported, MissingPackage, UndetectableIdleState
from .os_modules import __all__ as _os_modules

__all__ = (
    "__version__",
    "__version_info__",
    "MachineNotSupported",
    "MissingPackage",
    "UndetectableIdleState",
    *_os_modules,
)
