"""Pluggable Meeting Transport Adapters (Tencent Meeting Desktop, Simulator, VooV Web)."""

from .base import JoinConfig, MeetingAdapter
from .mumu_android import MuMuAndroidAdapter
from .simulator import SimulatorAdapter
from .tencent_desktop import TencentMeetingDesktopAdapter
from .voov_web import VooVWebAdapter

__all__ = [
    "JoinConfig",
    "MeetingAdapter",
    "MuMuAndroidAdapter",
    "SimulatorAdapter",
    "TencentMeetingDesktopAdapter",
    "VooVWebAdapter",
]
